from pm_assistant.core.matching import dedupe_evidence, text_matches_feature
from pm_assistant.core.models import Evidence, FeatureConfig


def test_feature_matching_uses_aliases_and_exclusions():
    config = FeatureConfig(feature_name="webhooks", aliases=["web hooks"], exclude_terms=["meeting webhook"])
    assert text_matches_feature("Need better web hooks for events", config)
    assert not text_matches_feature("meeting webhook docs", config)


def test_dedupe_removes_exact_repeats():
    item = Evidence(id="1", source="sample", source_type="note", title="A", text="Need auth", requester="Cust")
    duplicate = Evidence(id="2", source="sample", source_type="note", title="A", text="Need auth", requester="Cust")
    assert len(dedupe_evidence([item, duplicate])) == 1
