import json

import pytest

from denguesux import telegram


DATA = {"current": {"as_of": "2026-10-13", "areas": [
            {"code": "BD", "name": "Bedok", "risk": "High", "cluster_cases": 12, "cluster_count": 2},
            {"code": "JW", "name": "Jurong West", "risk": "Medium", "cluster_cases": 3, "cluster_count": 1},
            {"code": "TP", "name": "Toa Payoh", "risk": "Low", "cluster_cases": 0, "cluster_count": 0},
            {"code": "TE", "name": "Tengah", "risk": "Low", "cluster_cases": 0, "cluster_count": 0}]},
        "area_forecast": {"areas": [{"code": "BD", "band": "High", "band_now": "High", "p_high": 0.71},
                                     {"code": "TP", "band": "High", "band_now": "Low", "p_high": 0.56}]},
        "alerts": {"alerts": [{"kind": "new_cluster", "area_codes": ["JW"], "title": "New cluster: Jurong West St 41"}]}}
URL = "https://example.test"


class FakeBot:
    def __init__(self):
        self.sent = []

    def send(self, chat_id, text, keyboard=None):
        self.sent.append((chat_id, text))


def message(text, chat=42):
    return {"chat": {"id": chat, "type": "private"}, "text": text}


@pytest.fixture
def store(tmp_path):
    return telegram.FileSubscriptions(tmp_path)


def test_deep_link_start_subscribes_and_answers_with_dated_numbers(store):
    reply = telegram.handle(message("/start BD"), DATA, store, URL)
    assert reply.startswith("Subscribed to Bedok")
    assert "12 people in 2 active dengue clusters. Priority: High." in reply
    assert "NEA 13 Oct 2026" in reply and "Two-week outlook: High (71%" in reply
    assert f"{URL}/#plan/bedok" in reply
    assert store.areas_for(42) == ["BD"]
    assert "Already following" in telegram.handle(message("/start bedok"), DATA, store, URL)


def test_plain_area_names_resolve_by_prefix_but_never_ambiguously(store):
    assert telegram.handle(message("jurong"), DATA, store, URL).startswith("Jurong West · NEA")
    assert "New cluster: Jurong West St 41" in telegram.handle(message("Jurong West"), DATA, store, URL)
    assert "did not recognise" in telegram.handle(message("t"), DATA, store, URL)  # Toa Payoh or Tengah
    assert "did not recognise" in telegram.handle(message("Atlantis"), DATA, store, URL)
    assert store.all() == []  # reading never subscribes


def test_stop_deletes_everything_about_the_chat(store):
    telegram.handle(message("/subscribe Bedok"), DATA, store, URL)
    telegram.handle(message("/subscribe Toa Payoh"), DATA, store, URL)
    telegram.handle(message("/subscribe Bedok", chat=7), DATA, store, URL)
    assert "Stopped alerts for Toa Payoh" in telegram.handle(message("/unsubscribe toa payoh"), DATA, store, URL)
    assert "deleted" in telegram.handle(message("/stop"), DATA, store, URL)
    assert store.all() == [(7, "BD")]
    assert "no subscriptions" in telegram.handle(message("/stop"), DATA, store, URL)
    assert "not following any area" in telegram.handle(message("/status"), DATA, store, URL)


def test_areas_lists_only_high_and_medium_and_help_mentions_privacy(store):
    reply = telegram.handle(message("/areas"), DATA, store, URL)
    assert "Bedok: 12 people, High" in reply and "Jurong West: 3 people, Medium" in reply and "Toa Payoh" not in reply
    assert "only this chat's id" in telegram.handle(message("/help"), DATA, store, URL)
    assert telegram.handle(message("/bogus@DengueSUXbot"), DATA, store, URL) == telegram.HELP
    assert telegram.handle({"chat": {"id": 1}, "sticker": {}}, DATA, store, URL) is None


def test_daily_push_covers_only_areas_with_a_signal_and_reports_counts_only(tmp_path, monkeypatch):
    store = telegram.FileSubscriptions(tmp_path)
    for chat, code in [(1, "BD"), (1, "TE"), (2, "TE"), (3, "TP"), (4, "JW")]:
        store.add(chat, code)
    messages = telegram.daily_messages(DATA, store.all(), URL)
    assert set(messages) == {1, 3, 4}  # chat 2 follows a quiet area
    assert "High priority today" in messages[1] and "Tengah" not in messages[1]
    assert "forecast to reach High within two weeks" in messages[3]
    assert "New cluster: Jurong West St 41" in messages[4]
    web = tmp_path / "output/web"
    web.mkdir(parents=True)
    for name in ("current", "area_forecast", "alerts"):
        (web / f"{name}.json").write_text(json.dumps(DATA[name]))
    bot = FakeBot()
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)
    result = telegram.push_daily(tmp_path, bot=bot, base_url=URL)
    assert result == {"status": "sent", "chats": 3, "sent": 3, "errors": 0}
    assert {c for c, _ in bot.sent} == {1, 3, 4}
    assert not any(str(chat) in json.dumps(result) for chat in (1, 3, 4) if str(chat) not in ("3",))  # counts only
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert telegram.push_daily(tmp_path, base_url=URL)["status"] == "no_token"


def test_status_needs_a_token_and_never_exposes_it(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert telegram.status() == {"available": False}
    with pytest.raises(ValueError):
        telegram.Bot("")
    assert "secret" not in telegram.create_statement("t.s.telegram_subscriptions").lower()
    assert "chat_id BIGINT" in telegram.create_statement("t.s.telegram_subscriptions")
