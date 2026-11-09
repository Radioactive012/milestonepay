import base64

import pytest

from app.config import get_settings
from tests.test_portal import active_contract, upload


def basic(password, user="judge"):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


@pytest.fixture
def locked(api, monkeypatch):
    """The app with a password; the contract is made before locking, like the freelancer would."""
    contract = active_contract(api)
    file_id = upload(api, contract["milestones"][1]["id"]).json()["id"]
    monkeypatch.setattr(get_settings(), "app_password", "s3cret-pass")
    return api, contract, file_id


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/contracts"),
        ("GET", "/api/contracts/1"),
        ("GET", "/api/files/1"),
        ("GET", "/api/suggestions"),
        ("GET", "/api/messages"),
        ("POST", "/api/demo/reset"),
        ("POST", "/api/demo/load"),
        ("GET", "/api/demo/clock"),
        ("POST", "/api/milestones/1/invoice"),
        ("GET", "/"),
        ("GET", "/api/PORTAL/x"),
        ("GET", "/api/portal"),
    ],
)
def test_freelancer_side_needs_the_password(locked, method, path):
    api, _, _ = locked
    response = api.request(method, path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")
    assert api.request(method, path, headers=basic("wrong")).status_code == 401


def test_right_password_works_with_any_user_name(locked):
    api, contract, file_id = locked
    assert api.get("/api/contracts", headers=basic("s3cret-pass")).status_code == 200
    assert api.get(f"/api/files/{file_id}", headers=basic("s3cret-pass", user="")).status_code == 200


@pytest.mark.parametrize("header", ["Basic not-base64!!", "Bearer s3cret-pass", "Basic " + base64.b64encode(b"s3cret-pass").decode()])
def test_odd_login_headers_are_refused(locked, header):
    api, _, _ = locked
    assert api.get("/api/contracts", headers={"Authorization": header}).status_code == 401


def test_client_page_paypal_and_health_stay_open(locked):
    api, contract, file_id = locked
    token = contract["portal_token"]
    assert api.get(f"/api/portal/{token}").status_code == 200
    assert api.get(f"/api/portal/{token}/files/{file_id}").status_code == 402  # still locked until paid
    assert api.get(f"/api/portal/{token}/files/{file_id}/preview").status_code == 200
    assert api.get("/health").status_code == 200
    assert api.post("/webhooks/paypal", json={"id": "E1", "event_type": "X"}).status_code == 200


def test_client_cant_skip_payment_with_the_freelancer_address(locked):
    api, contract, file_id = locked
    assert api.get(f"/api/files/{file_id}").status_code == 401


def test_no_password_means_nothing_is_locked(api):
    assert api.get("/api/contracts").status_code == 200


# Uploaded files can never run as a web page


@pytest.mark.parametrize(
    "name, content_type, data",
    [
        ("page.html", "text/html", b"<script>alert(1)</script>"),
        ("logo.svg", "image/svg+xml", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
    ],
)
def test_uploaded_pages_are_always_downloads(api, name, content_type, data):
    contract = active_contract(api)
    deposit = contract["milestones"][0]
    file_id = upload(api, deposit["id"], name, data, content_type).json()["id"]
    api.post("/webhooks/paypal", json={"id": "E1", "event_type": "INVOICING.INVOICE.PAID",
                                       "resource": {"invoice": {"id": deposit["invoice"]["paypal_invoice_id"]}}})
    for url in (f"/api/files/{file_id}", f"/api/portal/{contract['portal_token']}/files/{file_id}"):
        response = api.get(url)
        assert response.status_code == 200
        assert response.headers["content-disposition"].startswith("attachment;")
        assert response.headers["x-content-type-options"] == "nosniff"
    # an SVG gets no preview, so it is never shown inline either
    assert api.get(f"/api/portal/{contract['portal_token']}/files/{file_id}/preview").status_code == 404


@pytest.mark.parametrize(
    "name, expected",
    [
        # the test client sends quote and line breaks as %22 %0D %0A; either way none survive
        ('evil"\r\nSet-Cookie: x=1.png', "evil_22_0D_0ASet-Cookie_ x_1.png"),
        ('evil"; x=.png', "evil_22_ x_.png"),
        ("résumé 日本.pdf", "r_sum_ __.pdf"),
        ("a" * 300 + ".png", "a" * 120),
        ("C:\\Users\\me\\logo.png", "logo.png"),
    ],
)
def test_odd_file_names_are_cleaned(api, name, expected):
    contract = active_contract(api)
    response = upload(api, contract["milestones"][1]["id"], name, b"data", "application/pdf")
    assert response.status_code == 201
    assert response.json()["filename"] == expected
    download = api.get(f"/api/files/{response.json()['id']}")
    assert download.headers["content-disposition"] == f'attachment; filename="{expected}"'


def test_huge_webhook_body_is_refused_before_paypal_is_asked(api, fake_paypal):
    response = api.post("/webhooks/paypal", content=b"{" + b" " * 1_100_000 + b"}",
                        headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert fake_paypal.calls == []
