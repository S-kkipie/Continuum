from continuum_api.models import (
    Document,
    IngestionJob,
    KnowledgeSource,
    Role,
    Successor,
)


def test_capture_models_have_expected_tablenames():
    assert Role.__tablename__ == "role"
    assert Successor.__tablename__ == "successor"
    assert KnowledgeSource.__tablename__ == "knowledge_source"
    assert Document.__tablename__ == "document"
    assert IngestionJob.__tablename__ == "ingestion_job"


def test_successor_status_defaults_to_provisioning():
    s = Successor(role_id="r1", knowledge_base_name="kb-o1-r1")
    assert s.status == "provisioning"
