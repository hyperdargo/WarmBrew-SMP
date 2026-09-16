import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    sys.modules.pop("app", None)
    import app as app_module

    app_module.app.config.update(TESTING=True)
    monkeypatch.setattr(
        app_module,
        "ping_minecraft",
        lambda host, port, timeout=3.0: {
            "players": {"online": 3, "max": 67},
            "version": {"name": "26.2"},
            "description": {"text": "", "extra": [{"text": "§6WarmBrew SMP"}, {"text": " hi"}]},
        },
    )
    app_module._status_cache.update(at=0.0, data=None)
    app_module.limiter = app_module.RateLimiter()
    with app_module.app.test_client() as c:
        c.app_module = app_module
        yield c


def csrf(client, path="/forum"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


@pytest.mark.parametrize("path", ["/", "/play", "/guide", "/forum", "/robots.txt", "/sitemap.xml", "/site.webmanifest"])
def test_pages_render(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert "Content-Security-Policy" in resp.headers


def test_unknown_page_is_404(client):
    resp = client.get("/nope")
    assert resp.status_code == 404
    assert b"Nothing out here" in resp.data


def test_legacy_image_route(client):
    assert client.get("/image/favicon-32x32.png").status_code == 200
    assert client.get("/image/../app.py").status_code == 404


def test_status_parses_ping(client):
    data = client.get("/api/status").get_json()
    assert data["online"] is True
    assert data["players"] == 3 and data["max"] == 67
    assert data["motd"] == "WarmBrew SMP hi"


def test_status_offline(client, monkeypatch):
    def boom(*a, **k):
        raise OSError("down")

    monkeypatch.setattr(client.app_module, "ping_minecraft", boom)
    assert client.get("/api/status").get_json()["online"] is False


def test_post_requires_csrf(client):
    resp = client.post("/forum/new", data={"title": "Hello", "content": "Some content here"})
    assert resp.status_code == 400


def test_create_post_and_comment(client):
    token = csrf(client)
    resp = client.post("/forum/new", data={
        "csrf_token": token, "title": "<script>alert(1)</script>", "author": "", "content": "Raided a base at spawn.",
    })
    assert resp.status_code == 303
    post_url = resp.headers["Location"]

    page = client.get(post_url).get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<script>alert(1)</script>" not in page
    assert "Anonymous" in page

    resp = client.post(post_url + "/comment", data={"csrf_token": token, "content": "gg"})
    assert resp.status_code == 303
    assert "gg" in client.get(post_url).get_data(as_text=True)


def test_validation_errors(client):
    token = csrf(client)
    resp = client.post("/forum/new", data={"csrf_token": token, "title": "x", "content": "short"})
    assert resp.status_code == 422
    assert b"at least 3 characters" in resp.data


def test_comment_on_missing_post_is_404(client):
    token = csrf(client)
    resp = client.post("/forum/post/999/comment", data={"csrf_token": token, "content": "hello"})
    assert resp.status_code == 404


def test_post_rate_limit(client):
    token = csrf(client)
    codes = [
        client.post("/forum/new", data={"csrf_token": token, "title": f"Post {i}", "content": "Long enough content"}).status_code
        for i in range(4)
    ]
    assert codes == [303, 303, 303, 429]


def test_honeypot_drops_bots(client):
    token = csrf(client)
    client.post("/forum/new", data={"csrf_token": token, "title": "Spam", "content": "Buy stuff now", "website": "x"})
    assert b"Spam" not in client.get("/forum").data


def test_oversized_body_rejected(client):
    token = csrf(client)
    resp = client.post("/forum/new", data={"csrf_token": token, "title": "Big", "content": "a" * 70_000})
    assert resp.status_code == 413
