from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.frontend import mount_frontend


def built_site(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("do not serve")
    app = FastAPI()

    @app.get("/api/real")
    def real():
        return {"ok": True}

    assert mount_frontend(app, tmp_path)
    return TestClient(app)


def test_screens_and_api_share_one_site(tmp_path):
    client = built_site(tmp_path)
    assert client.get("/").text == "<div id=root></div>"
    assert client.get("/portal/abc123").text == "<div id=root></div>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/api/real").json() == {"ok": True}


def test_unknown_api_addresses_stay_404(tmp_path):
    client = built_site(tmp_path)
    assert client.get("/api/nothing-here").status_code == 404
    assert client.get("/webhooks/nope").status_code == 404


def test_files_outside_the_build_are_never_served(tmp_path):
    client = built_site(tmp_path)
    response = client.get("/../secret.txt")
    assert "do not serve" not in response.text
    response = client.get("/%2e%2e/secret.txt")
    assert "do not serve" not in response.text


def test_nothing_is_mounted_without_a_build(tmp_path):
    assert mount_frontend(FastAPI(), tmp_path) is False


def test_more_path_tricks_stay_inside_the_build(tmp_path):
    client = built_site(tmp_path)
    for path in ("/assets/../../secret.txt", "/assets/..%2f..%2fsecret.txt", "/..%2fsecret.txt",
                 f"/{tmp_path.parent}/secret.txt", "/%2e%2e%2fsecret.txt"):
        assert "do not serve" not in client.get(path).text, path


def test_page_is_rechecked_after_every_deploy(tmp_path):
    client = built_site(tmp_path)
    for path in ("/", "/portal/abc123"):
        assert client.get(path).headers["cache-control"] == "no-cache"
