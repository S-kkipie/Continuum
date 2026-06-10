from continuum_api.agent.prompts import build_system_prompt
from continuum_api.models import Role, Successor


def test_system_prompt_frames_the_role_and_grounding_rules():
    role = Role(id="r1", org_id="o1", title="Support Lead", description="Owns refunds")
    successor = Successor(id="s1", role_id="r1", knowledge_base_name="kb")
    prompt = build_system_prompt(role, successor)
    assert "Support Lead" in prompt
    # grounding contract is spelled out
    low = prompt.lower()
    assert "retrieve" in low
    assert "cite" in low or "citation" in low
    assert "don't" in low or "do not" in low  # the honest-fallback instruction


def test_system_prompt_falls_back_when_no_summary_or_description():
    role = Role(id="r2", org_id="o1", title="Ops Lead")  # no description
    successor = Successor(id="s2", role_id="r2", knowledge_base_name="kb")  # no summary
    prompt = build_system_prompt(role, successor)
    assert "Ops Lead" in prompt
    assert "this role" in prompt  # the default fallback is used
