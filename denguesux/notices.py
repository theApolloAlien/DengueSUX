"""Short multilingual drafts grounded only in exported gold facts and NEA steps.

Local mode is a clearly labelled deterministic template. The optional workspace
provider may arrange approved fact-bound sentences; it cannot add assertions.
Returned model sentences must match the supplied allowlist exactly, so numbers,
dates and preventive advice cannot drift. No resident information is accepted.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlparse

import requests

from .growth import SOURCE_URL, _atomic_json
from .runtime import ROOT

LANGUAGES = {"en": "English", "zh": "中文", "ms": "Bahasa Melayu", "ta": "தமிழ்"}
NEA_BLOCK_URL = "https://www.nea.gov.sg/dengue-zika/prevent-aedes-mosquito-breeding"
NEA_CHECKLIST_URL = "https://www.nea.gov.sg/dengue-zika/prevent-aedes-mosquito-breeding/other-preventive-measures"
GUIDANCE_CHECKED = "2026-09-24"
PROMPT_VERSION = "gold-only-notice-v1"
SYSTEM_PROMPT = """Prepare a brief resident dengue source-reduction notice in the requested language.
Use ONLY the supplied gold facts and approved_sentences. Return one JSON object:
{"sentences": [each approved sentence exactly once]}. The first sentence must remain first.
You may reorder only the five prevention-step sentences. Keep the final limitation last.
Do not add, translate, paraphrase, omit, or repeat sentences. Do not invent facts or dates,
claim causation, claim that mosquito breeding has been found, or recommend fogging.
This is a draft for human review. Aim for at most 80 words. No markdown or commentary."""

STEPS = {
    "en": ["Loosen hardened soil.", "Empty flowerpot plates.", "Overturn pails and wipe their rims.", "Replace water in vases.", "Keep roof gutters clear and apply BTI as directed."],
    "zh": ["松动硬化的泥土。", "倒空花盆托盘。", "倒置水桶并擦干桶缘。", "更换花瓶中的水。", "清理屋檐排水槽，并按说明使用BTI杀幼虫剂。"],
    "ms": ["Gemburkan tanah yang mengeras.", "Kosongkan alas pasu bunga.", "Terbalikkan baldi dan lap bibirnya.", "Tukar air di dalam jambangan bunga.", "Bersihkan talang bumbung dan gunakan BTI mengikut arahan."],
    "ta": ["கெட்டியான மண்ணைத் தளர்த்துங்கள்.", "பூந்தொட்டித் தட்டுகளில் உள்ள நீரை அகற்றுங்கள்.", "வாளிகளைக் கவிழ்த்து அவற்றின் விளிம்புகளைத் துடையுங்கள்.", "பூச்சாடிகளில் உள்ள நீரை மாற்றுங்கள்.", "கூரை வடிகால்களைச் சுத்தமாக வைத்திருந்து, வழிமுறைகளின்படி BTI பயன்படுத்துங்கள்."],
}


class NoticeProvider(Protocol):
    name: str

    def compose(self, facts: dict, language: str, sentences: list[str]) -> str: ...


class DatabricksFoundationModel:
    name = "Databricks Foundation Model API · constrained draft"

    def __init__(self, endpoint=None, host=None, session=None):
        self.endpoint = endpoint or os.environ.get("DATABRICKS_NOTICE_ENDPOINT", "")
        self.host = host or os.environ.get("DATABRICKS_HOST", "")
        self.session = session or requests.Session()

    def compose(self, facts, language, sentences):
        if not self.endpoint:
            raise RuntimeError("Workspace notice endpoint is not configured")
        headers = None
        # Unified workspace authentication supports notebook identities and OAuth.
        try:
            from databricks.sdk.core import Config
            config = Config(host=self.host or None)
            self.host = config.host
            headers = config.authenticate()
        except Exception:
            token = os.environ.get("DATABRICKS_TOKEN", "")
            if self.host and token:
                headers = {"Authorization": "Bearer " + token}
        parsed = urlparse(self.host)
        if not headers or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query:
            raise RuntimeError("Workspace authentication is unavailable")
        payload = {"messages": [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"gold_facts": facts, "language": LANGUAGES[language], "approved_sentences": sentences}, ensure_ascii=False)}],
                   "temperature": 0, "max_tokens": 700, "stream": False}
        # Do not log headers, request body, responses, or exception strings.
        response = self.session.post(self.host.rstrip("/") + "/serving-endpoints/" + quote(self.endpoint, safe="") + "/invocations",
                                     headers=headers, json=payload, timeout=(10, 35), allow_redirects=False)
        if response.status_code != 200:
            raise RuntimeError("Workspace notice generation failed")
        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError):
            raise RuntimeError("Workspace notice response was invalid") from None


def facts_for_area(area_code, root=ROOT):
    """Use only the current gold-derived area export; never query live facts here."""
    path = Path(root) / "output/web/current.json"
    data = json.loads(path.read_text())
    matches = [area for area in data["areas"] if area["code"] == area_code]
    if len(matches) != 1:
        raise ValueError("Unknown planning area")
    area = matches[0]
    retrieved = data.get("as_of")
    if not retrieved:
        raise ValueError("Dated source facts are required for a notice")
    snapshot_date = dt.datetime.fromisoformat(retrieved.replace("Z", "+00:00")).astimezone(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    return {"area_code": area["code"], "area_name": area["name"], "snapshot_date": snapshot_date,
            "cluster_count": int(area["cluster_count"]), "cluster_cases": int(area["cluster_cases"]),
            "source_retrieved_at": retrieved, "cluster_feature_updates": data.get("cluster_updated_range", []),
            "gold_table": "gold_area_priorities", "gold_export_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "count_meaning": "Cumulative reported cases in active clusters overlapping this planning area; not weekly incidence. Shared clusters may overlap another area.",
            "prevention_steps": STEPS, "prevention_guidance_checked": GUIDANCE_CHECKED,
            "sources": [{"name": "NEA active clusters · data.gov.sg", "url": SOURCE_URL, "retrieved_at": retrieved},
                        {"name": "NEA Mozzie Wipeout / BLOCK guidance", "url": NEA_BLOCK_URL, "checked_at": GUIDANCE_CHECKED},
                        {"name": "NEA home prevention checklist", "url": NEA_CHECKLIST_URL, "checked_at": GUIDANCE_CHECKED}]}


def _approved_sentences(facts, language):
    area, date, clusters = facts["area_name"], facts["snapshot_date"], facts["cluster_count"]
    if language == "en":
        intro = f"{area} residents: the {date} snapshot reports {clusters} active dengue cluster{'s' if clusters != 1 else ''} overlapping this area; please check for stagnant water." if clusters else f"{area} residents: no active dengue clusters were reported here in the {date} snapshot; please continue checking for stagnant water."
        limit = "These are places to check, not confirmed breeding sites."
    elif language == "zh":
        intro = f"{area}居民：{date}的资料记录有{clusters}个活跃骨痛热症感染群与本区重叠，请检查积水。" if clusters else f"{area}居民：{date}的资料未记录本区有活跃骨痛热症感染群；请继续检查积水。"
        limit = "这些是待检查地点，并非已确认的蚊虫滋生处。"
    elif language == "ms":
        intro = f"Penduduk {area}: rekod {date} melaporkan {clusters} kelompok denggi aktif meliputi kawasan ini. Periksa air bertakung." if clusters else f"Penduduk {area}: rekod {date} tidak melaporkan kelompok denggi aktif di sini. Teruskan pemeriksaan air bertakung."
        limit = "Ini tempat untuk diperiksa, bukan tempat pembiakan yang disahkan."
    else:
        intro = f"{area} குடியிருப்பாளர்களே: {date} பதிவில் இப்பகுதியில் {clusters} செயலில் உள்ள டெங்கி நோய்த்தொற்றுக் குழுமங்கள் பதிவாகியுள்ளன. தேங்கிய நீரைச் சரிபாருங்கள்." if clusters else f"{area} குடியிருப்பாளர்களே: {date} பதிவில் இப்பகுதியில் செயலில் உள்ள டெங்கி நோய்த்தொற்றுக் குழுமங்கள் பதிவாகவில்லை. தேங்கிய நீரைத் தொடர்ந்து சரிபாருங்கள்."
        limit = "இவை சோதிக்க வேண்டிய இடங்கள்; உறுதிப்படுத்தப்பட்ட கொசு இனப்பெருக்க இடங்கள் அல்ல."
    return [intro, *facts["prevention_steps"][language], limit]


def _validated_model_text(raw, approved):
    """An exact sentence allowlist makes new health assertions impossible."""
    value = json.loads(raw)
    sentences = value.get("sentences")
    if not isinstance(sentences, list) or len(sentences) != len(approved):
        raise ValueError("Invalid notice sentence list")
    if any(not isinstance(item, str) for item in sentences):
        raise ValueError("Invalid notice sentence")
    if sentences[0] != approved[0] or sentences[-1] != approved[-1] or sorted(sentences[1:-1]) != sorted(approved[1:-1]):
        raise ValueError("Notice must preserve all approved facts and prevention steps")
    return " ".join(sentences)


def generate_notice(area_code, language="en", root=ROOT, provider=None):
    if language not in LANGUAGES:
        raise ValueError("Unsupported notice language")
    facts = facts_for_area(area_code, root)
    notice = _template_notice(area_code, language, facts)
    sentences = _approved_sentences(facts, language)
    if provider is None and os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        provider = DatabricksFoundationModel()
    if provider is not None:
        try:
            notice["text"] = _validated_model_text(provider.compose(facts, language, sentences), sentences)
            notice["mode"], notice["provider"] = "foundation_model", provider.name
        except Exception:
            notice["fallback_reason"] = "Workspace model unavailable or draft failed fact checks; using the local template."
    return notice


def write_notices(root=ROOT, spark=None):
    data = json.loads((Path(root) / "output/web/current.json").read_text())
    # Bulk/static exports always use deterministic templates, avoiding 220 paid calls.
    notices = {}
    for area in data["areas"]:
        notices[area["code"]] = {}
        facts = facts_for_area(area["code"], root)
        for language in LANGUAGES:
            notice = _template_notice(area["code"], language, facts)
            notices[area["code"]][language] = notice
    result = {"schema_version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "notices": notices,
              "languages": LANGUAGES, "label": "Draft: review before sending"}
    _atomic_json(Path(root) / "output/web/notices.json", result)
    if spark is not None:
        from .runtime import write_table
        rows = [(code, lang, notice["text"], notice["label"], notice["mode"], notice["source_facts"]["snapshot_date"], json.dumps(notice["source_facts"], ensure_ascii=False))
                for code, languages in notices.items() for lang, notice in languages.items()]
        write_table(spark.createDataFrame(rows, "area_code string, language string, notice_text string, label string, generation_mode string, as_of_date string, source_facts_json string"), "gold_resident_notices")
    return result


def _template_notice(area_code, language, facts):
    text = " ".join(_approved_sentences(facts, language))
    # Chinese has no whitespace word boundary; use a compact character budget.
    if (language == "zh" and len(text) > 350) or (language != "zh" and len(text.split()) > 80):
        raise ValueError("Notice exceeds its short-draft length budget")
    return {"area_code": area_code, "language": language, "language_name": LANGUAGES[language], "text": text,
            "label": "Draft: review before sending", "provider": "Local template fallback · no LLM used", "mode": "template",
            "fallback_reason": None, "prompt_version": PROMPT_VERSION, "source_facts": facts,
            "word_count": len(text.split()) if language != "zh" else None, "character_count": len(text),
            "review_note": "Review the translation, place names and dated facts before sharing. No notice is sent automatically.",
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
