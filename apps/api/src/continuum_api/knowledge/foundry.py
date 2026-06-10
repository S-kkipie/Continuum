from azure.identity import DefaultAzureCredential

from continuum_api.knowledge.interface import BlobStore
from continuum_api.knowledge.types import IndexingStatus, RetrievedSnippet

# api-version 2026-04-01 is the GA Knowledge Bases / agentic retrieval surface.
_API_VERSION = "2026-04-01"


class FoundryKnowledgeClient:
    """Real FoundryKnowledge over Azure AI Search knowledge bases (api-version 2026-04-01).

    SDK shape notes (verified against azure-search-documents==12.0.0):

    * Knowledge-base management uses ``SearchIndexClient`` (NOT ``KnowledgeBaseClient`` — that
      class does not exist in 12.0.0).  Methods: ``create_or_update_knowledge_base(kb)``,
      ``create_or_update_knowledge_source(source)``, ``get_knowledge_source_status(name)``.

    * Retrieval uses ``KnowledgeBaseRetrievalClient`` from
      ``azure.search.documents.knowledgebases`` (NOT ``KnowledgeRetrievalClient`` from the
      top-level package — that class also does not exist).  The client takes ``(endpoint,
      credential)`` and the knowledge-base name is supplied per-request via
      ``KnowledgeBaseRetrievalRequest(knowledge_source_params=[...])``.

    * Indexing ("synchronization") is triggered by calling ``SearchIndexClient.run_indexer``
      on a conventional ``SearchIndexer`` that is associated with the blob source, or by relying
      on the scheduled interval set on the knowledge source.  ``SearchIndexClient`` has no
      ``run_knowledge_source()`` method; ``start_indexing`` below delegates to
      ``SearchIndexerClient.run_indexer``.  The run ID returned is the knowledge-source name
      (used as the stable token for status checks).

    * ``indexing_status`` reads from ``KnowledgeSourceStatus``.  The model exposes
      ``synchronization_status`` ("creating" | "active" | "deleting") and
      ``current_synchronization_state`` (a ``SynchronizationState`` with
      ``items_updates_processed``, ``items_updates_failed``, ``errors``).

    * ``retrieve`` returns a ``KnowledgeBaseRetrievalResponse`` with a ``references`` list of
      ``KnowledgeBaseReference`` objects (discriminated by ``type``).  Each reference carries
      ``id`` (the document id), ``reranker_score``, and ``source_data`` (a free-form dict that
      may contain ``content`` / ``title`` / ``blobUrl`` depending on source type and whether
      ``include_reference_source_data=True`` was set on the source params).

    This is the ONLY file to change if the SDK surface differs from what is documented here.
    The interface (knowledge/interface.py) is stable.
    """

    def __init__(self, endpoint: str, blob: BlobStore) -> None:
        self._endpoint = endpoint
        self._blob = blob
        self._credential = DefaultAzureCredential()

    def _index_client(self):
        # Stateless remote client; constructed per call (no shared connection state).
        from azure.search.documents.indexes import SearchIndexClient

        return SearchIndexClient(self._endpoint, self._credential, api_version=_API_VERSION)

    def ensure_knowledge_base(self, name: str) -> str:
        """Create or update an Azure AI Search knowledge base with the given name.

        Returns the knowledge-base name (stable handle used by callers).
        """
        from azure.search.documents.indexes.models import KnowledgeBase, KnowledgeSourceReference

        client = self._index_client()
        kb = KnowledgeBase(name=name, knowledge_sources=[KnowledgeSourceReference(name=name)])
        client.create_or_update_knowledge_base(kb)
        return name

    def ensure_blob_source(self, kb: str, container: str) -> str:
        """Create or update an Azure Blob knowledge source and attach it to the knowledge base.

        The source name mirrors the knowledge-base name for simplicity (one source per KB in
        the capture loop).  Returns a ``kb::container`` compound key for caller tracking.
        """
        from azure.search.documents.indexes.models import (
            AzureBlobKnowledgeSource,
            AzureBlobKnowledgeSourceParameters,
        )

        client = self._index_client()
        # UNVERIFIED: connection_string format for managed identity (DefaultAzureCredential).
        # Hypothesis: the blob service URL; may instead require a ResourceId-style URI.
        # Confirm on the first real IT run (see class docstring).
        if not hasattr(self._blob, "_client"):
            raise ValueError(
                "FoundryKnowledgeClient requires an AzureBlobStore "
                "(expected _client.url on the BlobStore to derive the source connection string)"
            )
        connection_string = self._blob._client.url  # type: ignore[attr-defined]
        source = AzureBlobKnowledgeSource(
            name=kb,
            azure_blob_parameters=AzureBlobKnowledgeSourceParameters(
                connection_string=connection_string,
                container_name=container,
            ),
        )
        client.create_or_update_knowledge_source(source)
        return f"{kb}::{container}"

    def start_indexing(self, kb: str) -> str:
        """Trigger a synchronization run for the knowledge source.

        Azure AI Search knowledge sources synchronize via ``SearchIndexerClient.run_indexer``
        when a conventional indexer is wired to the blob source.  The knowledge-source name
        is returned as the opaque run-ID token; callers pass it back to ``indexing_status``.

        NOTE: if no conventional indexer is configured (only a knowledge source), trigger
        synchronization via a REST call or rely on the ``ingestionSchedule``.  The knowledge
        source will self-synchronize on its schedule; ``start_indexing`` here serves as the
        trigger signal.
        """
        from azure.search.documents.indexes import SearchIndexerClient

        client = SearchIndexerClient(self._endpoint, self._credential, api_version=_API_VERSION)
        client.run_indexer(kb)  # kb name doubles as indexer name for the paired indexer
        return kb  # stable run-ID: use KB name for status polling

    def indexing_status(self, run: str) -> IndexingStatus:
        """Return the current synchronization status for a knowledge source.

        ``run`` is the opaque token returned by ``start_indexing`` (the knowledge-source name).
        Returns IndexingStatus with state set to Azure's synchronization_status verbatim
        (no translation). UNVERIFIED: which status values are terminal vs in-progress —
        confirm on the first real IT run and update the poll loop's exit condition.
        Current sync state fields (``items_updates_processed``, ``items_updates_failed``,
        ``errors``) are read from ``current_synchronization_state`` when available.
        """
        client = self._index_client()
        s = client.get_knowledge_source_status(run)
        state = str(s.synchronization_status or "running")
        cur = s.current_synchronization_state
        indexed = int(cur.items_updates_processed) if cur else 0
        failed = int(cur.items_updates_failed) if cur else 0
        errors: list[str] = []
        if cur and cur.errors:
            errors = [e.error_message or "" for e in cur.errors]
        return IndexingStatus(state=state, indexed=indexed, failed=failed, errors=errors)

    def retrieve(self, kb: str, query: str, *, top: int = 5) -> list[RetrievedSnippet]:
        """Retrieve snippets from the knowledge base for the given query.

        Uses ``KnowledgeBaseRetrievalClient`` from ``azure.search.documents.knowledgebases``.
        The knowledge-base name is threaded through ``AzureBlobKnowledgeSourceParams`` in the
        request; ``include_reference_source_data=True`` populates ``reference.source_data``
        with document content for snippet extraction.

        References in the response carry:
          - ``id``             → ``source_document_id``
          - ``reranker_score`` → ``score``
          - ``source_data``    → dict that may contain "content", "title", "blobUrl"
        """
        from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
        from azure.search.documents.knowledgebases.models import (
            AzureBlobKnowledgeSourceParams,
            KnowledgeBaseRetrievalRequest,
        )

        client = KnowledgeBaseRetrievalClient(
            self._endpoint, self._credential, api_version=_API_VERSION
        )
        request = KnowledgeBaseRetrievalRequest(
            knowledge_source_params=[
                AzureBlobKnowledgeSourceParams(
                    knowledge_source_name=kb,
                    include_references=True,
                    include_reference_source_data=True,
                    reranker_threshold=0.0,
                )
            ],
            # `top` approximated via token budget (~512 tok/ref); the API has no direct
            # "top N references" param. Hard-capped post-response below.
            max_output_size_in_tokens=top * 512,
        )
        response = client.retrieve(request)
        snippets: list[RetrievedSnippet] = []
        for ref in response.references or []:
            sd = ref.source_data or {}
            content = sd.get("content") or sd.get("blobUrl") or ref.id or ""
            title = sd.get("title") or sd.get("blobUrl") or ref.id or ""
            snippets.append(
                RetrievedSnippet(
                    content=str(content),
                    title=str(title),
                    source_document_id=str(ref.id or ""),
                    score=float(ref.reranker_score or 0.0),
                )
            )
            if len(snippets) >= top:
                break
        return snippets
