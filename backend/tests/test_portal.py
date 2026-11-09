from io import BytesIO

import pytest
from PIL import Image

from app import files as files_module
from app.files import make_preview, safe_filename
from tests.conftest import CONTRACT_TEXT


def png_bytes(size=(1600, 1000), colour=(30, 120, 200)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, colour).save(buffer, "PNG")
    return buffer.getvalue()


def active_contract(api, deposit_pct=30) -> dict:
    contract = api.post("/api/contracts", data={"client_email": "buyer@example.com", "text": CONTRACT_TEXT}).json()
    return api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": deposit_pct}).json()


def upload(api, milestone_id, name="logo.png", data=None, content_type="image/png"):
    return api.post(
        f"/api/milestones/{milestone_id}/files",
        files={"file": (name, data if data is not None else png_bytes(), content_type)},
    )


def pay(api, event_id, paypal_invoice_id):
    return api.post(
        "/webhooks/paypal",
        json={"id": event_id, "event_type": "INVOICING.INVOICE.PAID", "resource": {"invoice": {"id": paypal_invoice_id}}},
    )


def test_safe_filename():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename('Final "logo".png') == "Final _logo_.png"
    assert safe_filename(None) == "file"
    assert safe_filename("...") == "file"


def test_preview_is_smaller_watermarked_jpeg():
    original = png_bytes()
    preview = make_preview(original, "image/png")
    image = Image.open(BytesIO(preview))
    assert image.format == "JPEG"
    assert max(image.size) == files_module.PREVIEW_MAX_SIDE
    # the watermark changes pixels, so it's not a plain blue square any more
    assert len(image.convert("RGB").getcolors(maxcolors=1_000_000)) > 10
    assert make_preview(b"%PDF-1.4 fake", "application/pdf") is None
    assert make_preview(b"not really a png", "image/png") is None


def test_freelancer_upload_shows_on_contract(api):
    contract = active_contract(api)
    sketches = contract["milestones"][1]
    assert upload(api, sketches["id"]).status_code == 201
    assert upload(api, sketches["id"], "brief.pdf", b"%PDF-1.4 fake", "application/pdf").status_code == 201
    files = api.get(f"/api/contracts/{contract['id']}").json()["milestones"][1]["files"]
    assert [(f["filename"], f["has_preview"], f["locked"]) for f in files] == [
        ("logo.png", True, True),
        ("brief.pdf", False, True),
    ]


def test_upload_limits(api, monkeypatch):
    contract = active_contract(api)
    milestone_id = contract["milestones"][1]["id"]
    assert upload(api, milestone_id, data=b"").status_code == 422
    monkeypatch.setattr("app.api.portal.MAX_FILE_BYTES", 10)
    assert upload(api, milestone_id, data=b"x" * 11, content_type="text/plain").status_code == 422
    assert upload(api, 9999).status_code == 404


def test_portal_shows_client_view_only(api):
    contract = active_contract(api)
    view = api.get(f"/api/portal/{contract['portal_token']}").json()
    assert view["client_name"] == "Harbor Lane Bakery"
    assert view["total"] == "3200.00" and view["paid"] == "0.00" and view["outstanding"] == "3200.00"
    deposit = view["milestones"][0]
    assert deposit["is_deposit"] and deposit["invoice"]["payer_url"] == "https://pay.example/INV2-0001"
    assert deposit["can_approve"] is False
    assert view["milestones"][1]["can_approve"] is True
    for private in ("risks", "audit", "client_email", "hourly_rate", "portal_token", "warnings"):
        assert private not in view


def test_draft_contract_portal_shows_nothing_yet(api):
    contract = api.post("/api/contracts", data={"client_email": "b@example.com", "text": CONTRACT_TEXT}).json()
    view = api.get(f"/api/portal/{contract['portal_token']}").json()
    assert view["status"] == "draft" and view["milestones"] == []


def test_bad_link_is_404(api):
    assert api.get("/api/portal/not-a-real-token").status_code == 404


def test_files_locked_until_paid_then_unlock(api):
    contract = active_contract(api)
    token = contract["portal_token"]
    deposit = contract["milestones"][0]
    file_id = upload(api, deposit["id"], data=png_bytes()).json()["id"]

    locked = api.get(f"/api/portal/{token}/files/{file_id}")
    assert locked.status_code == 402
    preview = api.get(f"/api/portal/{token}/files/{file_id}/preview")
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/jpeg"

    assert pay(api, "WH-1", deposit["invoice"]["paypal_invoice_id"]).json() == {"status": "ok"}
    view = api.get(f"/api/portal/{token}").json()
    assert view["milestones"][0]["files"][0]["locked"] is False
    assert view["paid"] == "960.00"

    unlocked = api.get(f"/api/portal/{token}/files/{file_id}")
    assert unlocked.status_code == 200
    assert unlocked.content == png_bytes()
    assert 'filename="logo.png"' in unlocked.headers["content-disposition"]
    actions = [e["action"] for e in api.get(f"/api/contracts/{contract['id']}").json()["audit"]]
    assert "file_downloaded" in actions


def test_another_clients_link_cannot_reach_files(api):
    first = active_contract(api)
    second = active_contract(api)
    file_id = upload(api, first["milestones"][1]["id"]).json()["id"]
    assert api.get(f"/api/portal/{second['portal_token']}/files/{file_id}").status_code == 404
    assert api.get(f"/api/portal/{second['portal_token']}/files/{file_id}/preview").status_code == 404
    other_milestone = first["milestones"][1]["id"]
    assert api.post(f"/api/portal/{second['portal_token']}/milestones/{other_milestone}/approve").status_code == 404


def test_client_approval_invoices_event_milestone(api, fake_paypal):
    contract = active_contract(api)
    token = contract["portal_token"]
    sketches = contract["milestones"][1]
    view = api.post(f"/api/portal/{token}/milestones/{sketches['id']}/approve").json()
    approved = view["milestones"][1]
    assert approved["status"] == "invoiced"
    assert approved["invoice"]["payer_url"].startswith("https://pay.example/")
    assert api.post(f"/api/portal/{token}/milestones/{sketches['id']}/approve").status_code == 409

    audit = api.get(f"/api/contracts/{contract['id']}").json()["audit"]
    approval = next(e for e in audit if e["action"] == "client_approved")
    assert approval["actor"] == "client"


def test_client_approval_of_dated_milestone_is_recorded_only(api, fake_paypal):
    contract = active_contract(api)
    logo = contract["milestones"][2]
    assert logo["status"] == "scheduled"
    view = api.post(f"/api/portal/{contract['portal_token']}/milestones/{logo['id']}/approve").json()
    assert view["milestones"][2]["status"] == "scheduled"
    assert len(fake_paypal.invoices) == 1


def test_deposit_cannot_be_approved_by_client(api):
    contract = active_contract(api)
    deposit = contract["milestones"][0]
    response = api.post(f"/api/portal/{contract['portal_token']}/milestones/{deposit['id']}/approve")
    assert response.status_code == 409


@pytest.mark.parametrize("path", ["/api/files/9999", "/api/portal/x/files/1"])
def test_missing_files_are_404(api, path):
    assert api.get(path).status_code == 404
