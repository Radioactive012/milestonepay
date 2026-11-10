"""The printable evidence pack for a payment dispute."""
import hashlib

from tests.test_portal import active_contract, pay, png_bytes, upload


def test_evidence_pack_has_the_whole_story(api, session, fake_paypal):
    contract = active_contract(api)
    deposit = contract["milestones"][0]
    sketches = contract["milestones"][1]
    data = png_bytes()
    upload(api, deposit["id"], name="logo.png", data=data)
    token = contract["portal_token"]
    api.post(f"/api/portal/{token}/messages", json={"body": "Looks great, <b>thanks</b>!"})
    api.post(f"/api/portal/{token}/milestones/{sketches['id']}/approve")
    pay(api, "WH-E1", deposit["invoice"]["paypal_invoice_id"])

    response = api.get(f"/api/contracts/{contract['id']}/evidence")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    page = response.text
    assert contract["client_name"] in page
    assert deposit["invoice"]["number"] in page and "PAID" in page
    assert hashlib.sha256(data).hexdigest() in page          # proves which file was delivered
    assert "client approved" in page                          # from the audit log
    # what the client typed is shown as text, never run as HTML
    assert "&lt;b&gt;thanks&lt;/b&gt;" in page and "<b>thanks</b>" not in page
    assert "Print or save as PDF" in page


def test_evidence_pack_for_unknown_project_is_404(api):
    assert api.get("/api/contracts/999/evidence").status_code == 404
