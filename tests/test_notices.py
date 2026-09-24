import json

import pytest

from denguesux.notices import LANGUAGES, generate_notice, write_notices


@pytest.fixture
def notice_root(tmp_path):
    path = tmp_path / "output/web/current.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"as_of": "2026-09-24T04:00:34+00:00", "cluster_updated_range": ["20260918151158"], "areas": [
        {"code": "JE", "name": "Jurong East", "cluster_count": 2, "cluster_cases": 76},
        {"code": "XX", "name": "Central Water Catchment", "cluster_count": 0, "cluster_cases": 0}]}))
    return tmp_path


@pytest.mark.parametrize("language", LANGUAGES)
def test_four_short_dated_template_drafts_with_source_facts(notice_root, language):
    result = generate_notice("JE", language, notice_root)
    assert result["mode"] == "template" and "no LLM" in result["provider"]
    assert result["label"] == "Draft: review before sending"
    assert "Jurong East" in result["text"] and "2026-09-24" in result["text"]
    assert result["source_facts"]["cluster_cases"] == 76
    assert len(result["source_facts"]["prevention_steps"][language]) == 5
    if language != "zh":
        assert result["word_count"] <= 80


def test_zero_clusters_does_not_claim_zero_dengue(notice_root):
    result = generate_notice("XX", "en", notice_root)
    assert "no active dengue clusters were reported" in result["text"]
    assert "zero dengue" not in result["text"]
    assert result["word_count"] <= 80


def test_llm_fact_invention_falls_back_without_leaking_error(notice_root):
    class Invents:
        name = "Test model"
        def compose(self, facts, language, sentences):
            return json.dumps({"sentences": ["Mosquito breeding found at block 100"] + sentences[1:]})
    result = generate_notice("JE", "en", notice_root, provider=Invents())
    assert result["mode"] == "template" and result["fallback_reason"]
    assert "block 100" not in result["text"]


def test_llm_exact_gold_sentence_composition_is_accepted(notice_root):
    class Composes:
        name = "Test model"
        def compose(self, facts, language, sentences):
            return json.dumps({"sentences": [sentences[0], *reversed(sentences[1:-1]), sentences[-1]]})
    result = generate_notice("JE", "ms", notice_root, provider=Composes())
    assert result["mode"] == "foundation_model"


def test_llm_error_content_is_never_exposed(notice_root):
    class Fails:
        name = "Test model"
        def compose(self, facts, language, sentences):
            raise RuntimeError("example_secret_never_expose_this")
    result = generate_notice("JE", "en", notice_root, provider=Fails())
    assert "example_secret" not in json.dumps(result)


def test_static_exports_never_invoke_workspace_model(notice_root, monkeypatch):
    monkeypatch.setenv("DATABRICKS_RUNTIME_VERSION", "fixture")
    result = write_notices(notice_root)
    assert len(result["notices"]) == 2
    assert all(notice["mode"] == "template" for languages in result["notices"].values() for notice in languages.values())
    assert (notice_root / "output/web/notices.json").exists()


def test_unknown_area_or_language_is_rejected(notice_root):
    with pytest.raises(ValueError, match="Unknown planning area"):
        generate_notice("bad", "en", notice_root)
    with pytest.raises(ValueError, match="Unsupported"):
        generate_notice("JE", "bad", notice_root)
