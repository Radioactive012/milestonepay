"""The client's message box on their page, and the freelancer's Analyse / Dismiss buttons."""
from sqlmodel import select

from app.models import AuditEntry, ClientNote, Message, Suggestion
from tests.test_messages_api import MESSAGE, message_ai  # noqa: F401 (pytest fixture)
from tests.test_portal import active_contract

DRAFT_CONTRACT = {"client_email": "b@example.com"}


def write(api, token, body=MESSAGE):
    return api.post(f"/api/portal/{token}/messages", json={"body": body})


def test_client_message_is_saved_without_any_ai_call(api, session, message_ai):
    contract = active_contract(api)
    response = write(api, contract["portal_token"], f"  {MESSAGE}  ")
    assert response.status_code == 201
    assert response.json()["messages"][0]["body"] == MESSAGE
    assert message_ai.calls == 0
    assert session.exec(select(Message)).all() == []  # nothing in the AI inbox yet
    entry = session.exec(select(AuditEntry).where(AuditEntry.action == "client_message")).one()
    assert entry.actor == "client"
    notes = api.get(f"/api/contracts/{contract['id']}/client-messages").json()
    assert [(n["body"], n["status"]) for n in notes] == [(MESSAGE, "waiting")]


def test_client_page_shows_their_own_messages(api):
    contract = active_contract(api)
    write(api, contract["portal_token"], "First")
    write(api, contract["portal_token"], "Second")
    view = api.get(f"/api/portal/{contract['portal_token']}").json()
    assert [m["body"] for m in view["messages"]] == ["Second", "First"]


def test_analyse_sends_it_through_the_usual_message_reading(api, session, message_ai):
    contract = active_contract(api)
    write(api, contract["portal_token"])
    note_id = api.get(f"/api/contracts/{contract['id']}/client-messages").json()[0]["id"]

    result = api.post(f"/api/client-messages/{note_id}/analyse")
    assert result.status_code == 200, result.text
    assert message_ai.calls == 1
    assert result.json()["message"]["sender"] == "client"
    assert len(session.exec(select(Suggestion)).all()) == len(result.json()["suggestions"]) > 0
    note = session.get(ClientNote, note_id)
    assert note.status == "analysed" and note.message_id == result.json()["message"]["id"]

    # a second click costs no AI credit
    again = api.post(f"/api/client-messages/{note_id}/analyse")
    assert again.status_code == 409 and message_ai.calls == 1


def test_failed_ai_reading_leaves_the_message_waiting(api, session, message_ai):
    contract = active_contract(api)
    write(api, contract["portal_token"])
    note_id = api.get(f"/api/contracts/{contract['id']}/client-messages").json()[0]["id"]
    message_ai.failures = 1
    assert api.post(f"/api/client-messages/{note_id}/analyse").status_code == 502
    session.expire_all()
    assert session.get(ClientNote, note_id).status == "waiting"


def test_dismiss_handles_it_without_ai(api, session, message_ai):
    contract = active_contract(api)
    write(api, contract["portal_token"])
    note_id = api.get(f"/api/contracts/{contract['id']}/client-messages").json()[0]["id"]
    assert api.post(f"/api/client-messages/{note_id}/dismiss").json()["status"] == "dismissed"
    assert api.post(f"/api/client-messages/{note_id}/analyse").status_code == 409
    assert message_ai.calls == 0


def test_client_message_limits(api, monkeypatch):
    import app.api.portal as portal

    draft = api.post("/api/contracts", data={**DRAFT_CONTRACT, "text": "x" * 50}).json()
    assert write(api, draft["portal_token"]).status_code == 409  # not started yet

    contract = active_contract(api)
    token = contract["portal_token"]
    assert write(api, token, "   ").status_code == 422
    assert write(api, token, "x" * (portal.MAX_CLIENT_NOTE_CHARS + 1)).status_code == 422
    assert write(api, "not-a-real-link").status_code == 404

    monkeypatch.setattr(portal, "MAX_WAITING_NOTES", 2)
    assert write(api, token).status_code == 201
    assert write(api, token).status_code == 201
    assert write(api, token).status_code == 429


def test_unknown_message_and_project(api):
    assert api.post("/api/client-messages/999/analyse").status_code == 404
    assert api.get("/api/contracts/999/client-messages").status_code == 404
