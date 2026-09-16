"""WarmBrew SMP website.

Single-file Flask app so it runs as-is on a Pterodactyl Python egg:
the panel installs requirements.txt and starts `python app.py`.

Configuration is environment-only (all optional):
    SERVER_PORT / PORT   port to listen on (Pterodactyl sets SERVER_PORT)   default 25598
    SECRET_KEY           session signing key (auto-generated to .secret_key if unset)
    SITE_URL             public base URL, e.g. https://<your-website-domain> (canonical + sitemap)
    MC_HOST / MC_PORT    Minecraft server to ping for live status            default warmbrew.ankitgupta.com.np:25599
    DISCORD_URL          Discord invite; the Discord link is hidden until this is set
    DATABASE_PATH        SQLite file for the forum                            default ./warmbrew.db
    COOKIE_SECURE=1      mark cookies Secure (only when served over HTTPS)
    TRUST_PROXY=1        trust one reverse proxy's X-Forwarded-* headers
"""

import json
import math
import os
import re
import secrets
import socket
import sqlite3
import struct
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from flask import (
    Flask,
    Response,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "warmbrew.db"))

SERVER_IP = "warmbrew.ankitgupta.com.np"
MC_HOST = os.environ.get("MC_HOST", SERVER_IP)
MC_PORT = int(os.environ.get("MC_PORT", "25599"))
DISCORD_URL = os.environ.get("DISCORD_URL", "").strip()
SITE_URL = os.environ.get("SITE_URL", "").strip().rstrip("/")

LIMITS = {"title": 120, "author": 32, "post": 5000, "comment": 2000}
POSTS_PER_PAGE = 15


def _load_secret_key():
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    key_file = BASE_DIR / ".secret_key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_hex(32)
    key_file.write_text(key)
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
    return key


app = Flask(__name__)
app.config.update(
    SECRET_KEY=_load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
    MAX_CONTENT_LENGTH=64 * 1024,
    SEND_FILE_MAX_AGE_DEFAULT=60 * 60 * 24 * 7,
)

if os.environ.get("TRUST_PROXY") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


# --------------------------------------------------------------------------- content
# Facts about the server live here, once, so every page says the same thing.

SERVER = {
    "name": "WarmBrew SMP",
    "ip": SERVER_IP,
    "versions": "1.21.x – 26.x",
    "motd": "Sit back, relax & enjoy the survival vibe.",
}

REMOVED = [
    {
        "label": "Economy",
        "commands": ["/shop", "/auction", "/sell", "/bal", "/pay"],
        "note": "No economy. Pure barter and survival.",
    },
    {
        "label": "Travel",
        "commands": ["/tpa", "/home", "/spawn", "/back"],
        "note": "Walk, boat, or elytra. Vanilla travel only.",
    },
    {
        "label": "Protection",
        "commands": ["/claim"],
        "note": "No land claims. Build hidden, defend with traps.",
    },
    {
        "label": "Perks",
        "commands": ["/kit", "/fly"],
        "note": "Zero donor perks. Everyone plays equal.",
    },
]

PLUGINS = [
    {
        "group": "Accounts",
        "items": [
            ("AuthMe", "Account security: /register, /login, and /premium auto-login."),
            ("SkinsRestorer", "Skin support for both cracked and premium players."),
        ],
    },
    {
        "group": "Talking",
        "items": [
            ("Simple Voice Chat", "In-game proximity voice chat."),
            ("DiscordSRV", "Bridges server chat with Discord."),
            ("DTEmpire AI Chat", "A private in-game AI assistant."),
        ],
    },
    {
        "group": "Performance",
        "items": [
            ("Chunky", "Pre-generates world chunks for lag-free exploration."),
            ("Clumps", "Groups XP orbs together to reduce lag."),
            ("ViaVersion & ViaBackwards", "Lets clients from 1.21.x to 26.x connect."),
            ("FastAsyncWorldEdit", "Fast world editing for server maintenance."),
        ],
    },
    {
        "group": "Running the server",
        "items": [
            ("EssentialsX (Base, Chat, Spawn)", "Minimal utility, chat formatting and spawn point handling."),
            ("LuckPerms", "Permission management."),
            ("CommandBlocker", "Blocks sensitive admin commands and exploit vectors."),
            ("PacketEvents & PlaceholderAPI", "Backend dependencies for packets and placeholders."),
        ],
    },
]

AI_COMMANDS = [
    ("/aichat", "Enter private AI chat mode"),
    ("/aichat <message>", "Enter AI mode and send your first message"),
    ("/aiexit", "Leave AI chat mode"),
    ("/aic", "Alias for /aichat"),
    ("/aidone", "Alias for /aiexit"),
]

LINKS = {
    "ai_plugin": "https://github.com/hyperdargo/DTEmpireAiPlugin",
    "ai_plugin_releases": "https://github.com/hyperdargo/DTEmpireAiPlugin/releases",
    "modpack": "https://modrinth.com/modpack/dtempire-optimized",
    "discord": DISCORD_URL,
}


# --------------------------------------------------------------------------- database

SCHEMA = """
CREATE TABLE IF NOT EXISTS forum_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT,
    title TEXT,
    content TEXT,
    date TEXT,
    likes INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS forum_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER,
    author TEXT,
    content TEXT,
    date TEXT
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON forum_comments (post_id);
"""


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


init_db()


# --------------------------------------------------------------------------- security

@app.before_request
def csrf_protect():
    if request.method != "POST":
        return
    expected = session.get("_csrf")
    sent = request.form.get("csrf_token", "")
    if not expected or not secrets.compare_digest(expected, sent):
        abort(400, "Your session expired. Reload the page and try again.")


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' https://fonts.googleapis.com",
        "font-src https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return resp


class RateLimiter:
    """Sliding-window limiter kept in memory. One process, so this is enough."""

    def __init__(self):
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key, limit, window):
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 10_000:
                self._hits = defaultdict(deque, {k: q for k, q in self._hits.items() if q and now - q[-1] < 3600})
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True


limiter = RateLimiter()


# --------------------------------------------------------------------------- live server status

def _varint(n):
    n &= 0xFFFFFFFF
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            raise OSError("connection closed")
        buf += chunk
    return bytes(buf)


def _read_varint(sock):
    value = 0
    for i in range(5):
        byte = _recv_exact(sock, 1)[0]
        value |= (byte & 0x7F) << (7 * i)
        if not byte & 0x80:
            return value
    raise ValueError("varint too long")


def _flatten_text(component):
    if isinstance(component, str):
        return component
    if isinstance(component, list):
        return "".join(_flatten_text(c) for c in component)
    if isinstance(component, dict):
        return _flatten_text(component.get("text", "")) + _flatten_text(component.get("extra", []))
    return ""


def ping_minecraft(host, port, timeout=3.0):
    """Java Edition Server List Ping. Returns the server's status JSON."""
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        host_bytes = host.encode("utf-8")
        handshake = (
            _varint(0x00) + _varint(-1) + _varint(len(host_bytes)) + host_bytes
            + struct.pack(">H", port) + _varint(1)
        )
        sock.sendall(_varint(len(handshake)) + handshake + b"\x01\x00")
        _read_varint(sock)  # packet length
        if _read_varint(sock) != 0x00:
            raise ValueError("unexpected packet")
        size = _read_varint(sock)
        if size > 1_000_000:
            raise ValueError("status too large")
        return json.loads(_recv_exact(sock, size).decode("utf-8"))


_status_cache = {"at": 0.0, "data": None}
_status_lock = threading.Lock()
STATUS_TTL = 30


def server_status():
    with _status_lock:
        if _status_cache["data"] and time.monotonic() - _status_cache["at"] < STATUS_TTL:
            return _status_cache["data"]
        try:
            raw = ping_minecraft(MC_HOST, MC_PORT)
            players = raw.get("players") or {}
            motd = re.sub(r"§.", "", _flatten_text(raw.get("description", "")))
            data = {
                "online": True,
                "players": int(players.get("online", 0)),
                "max": int(players.get("max", 0)),
                "version": str((raw.get("version") or {}).get("name", ""))[:40],
                "motd": " ".join(motd.split())[:160],
            }
        except (OSError, ValueError, TypeError, AttributeError):
            data = {"online": False}
        data["checked"] = int(time.time())
        _status_cache.update(at=time.monotonic(), data=data)
        return data


# --------------------------------------------------------------------------- template helpers

_asset_versions = {}


def asset(path):
    """Static URL with a content-version query so browsers can cache for a week."""
    version = _asset_versions.get(path)
    if version is None or app.debug:
        try:
            version = str(int((STATIC_DIR / path).stat().st_mtime))
        except OSError:
            version = "0"
        _asset_versions[path] = version
    return url_for("static", filename=path, v=version)


def site_url():
    return SITE_URL or request.url_root.rstrip("/")


@app.template_filter("datefmt")
def datefmt(value):
    try:
        return datetime.fromisoformat(value).strftime("%d %b %Y, %H:%M")
    except (TypeError, ValueError):
        return value or ""


@app.template_filter("isodate")
def isodate(value):
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except (TypeError, ValueError):
        return ""


@app.context_processor
def inject_globals():
    return {
        "server": SERVER,
        "links": LINKS,
        "limits": LIMITS,
        "asset": asset,
        "csrf_token": csrf_token,
        "site_url": site_url(),
        "canonical": site_url() + request.path,
        "year": datetime.now().year,
    }


def clean_line(value, limit):
    return " ".join((value or "").split())[:limit]


def clean_text(value):
    text = (value or "").replace("\r\n", "\n").strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def client_key():
    return request.remote_addr or "unknown"


# --------------------------------------------------------------------------- pages

@app.route("/")
def index():
    latest = get_db().execute(
        """SELECT p.id, p.title, p.author, p.date, COUNT(c.id) AS comments
           FROM forum_posts p LEFT JOIN forum_comments c ON c.post_id = p.id
           GROUP BY p.id ORDER BY p.id DESC LIMIT 3"""
    ).fetchall()
    return render_template(
        "index.html", removed=REMOVED, plugins=PLUGINS, ai_commands=AI_COMMANDS, latest=latest
    )


@app.route("/play")
def play():
    return render_template("play.html", removed=REMOVED, ai_commands=AI_COMMANDS)


@app.route("/guide")
def guide():
    return render_template("guide.html", removed=REMOVED, ai_commands=AI_COMMANDS, plugins=PLUGINS)


def render_forum(page=1, errors=None, form=None, status=200):
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM forum_posts").fetchone()[0]
    pages = max(1, math.ceil(total / POSTS_PER_PAGE))
    page = min(max(page, 1), pages)
    posts = db.execute(
        """SELECT p.id, p.title, p.author, p.content, p.date, COUNT(c.id) AS comments
           FROM forum_posts p LEFT JOIN forum_comments c ON c.post_id = p.id
           GROUP BY p.id ORDER BY p.id DESC LIMIT ? OFFSET ?""",
        (POSTS_PER_PAGE, (page - 1) * POSTS_PER_PAGE),
    ).fetchall()
    return (
        render_template(
            "forum.html", posts=posts, page=page, pages=pages, total=total,
            errors=errors or {}, form=form or {},
        ),
        status,
    )


@app.route("/forum")
def forum():
    return render_forum(page=request.args.get("page", 1, type=int))


@app.route("/forum/new", methods=["POST"])
def create_post():
    form = {
        "title": clean_line(request.form.get("title"), LIMITS["title"]),
        "author": clean_line(request.form.get("author"), LIMITS["author"]),
        "content": clean_text(request.form.get("content")),
    }
    if request.form.get("website"):  # honeypot: humans never see this field
        return redirect(url_for("forum"))

    errors = {}
    if len(form["title"]) < 3:
        errors["title"] = "Give your post a title (at least 3 characters)."
    if len(form["content"]) < 10:
        errors["content"] = "Write at least 10 characters."
    elif len(form["content"]) > LIMITS["post"]:
        errors["content"] = f"Keep it under {LIMITS['post']} characters."
    if errors:
        return render_forum(errors=errors, form=form, status=422)
    if not limiter.hit(("post", client_key()), limit=3, window=600):
        errors["form"] = "You've posted a lot in the last few minutes. Wait a bit and try again."
        return render_forum(errors=errors, form=form, status=429)

    db = get_db()
    cur = db.execute(
        "INSERT INTO forum_posts (author, title, content, date) VALUES (?, ?, ?, ?)",
        (form["author"] or "Anonymous", form["title"], form["content"], datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    return redirect(url_for("forum_post", post_id=cur.lastrowid), code=303)


def render_post(post_id, errors=None, form=None, status=200):
    db = get_db()
    post = db.execute("SELECT * FROM forum_posts WHERE id = ?", (post_id,)).fetchone()
    if post is None:
        abort(404)
    comments = db.execute(
        "SELECT * FROM forum_comments WHERE post_id = ? ORDER BY id ASC", (post_id,)
    ).fetchall()
    return (
        render_template("forum_post.html", post=post, comments=comments, errors=errors or {}, form=form or {}),
        status,
    )


@app.route("/forum/post/<int:post_id>")
def forum_post(post_id):
    return render_post(post_id)


@app.route("/forum/post/<int:post_id>/comment", methods=["POST"])
def add_comment(post_id):
    form = {
        "author": clean_line(request.form.get("author"), LIMITS["author"]),
        "content": clean_text(request.form.get("content")),
    }
    if request.form.get("website"):
        return redirect(url_for("forum_post", post_id=post_id))
    if get_db().execute("SELECT 1 FROM forum_posts WHERE id = ?", (post_id,)).fetchone() is None:
        abort(404)

    errors = {}
    if len(form["content"]) < 2:
        errors["content"] = "Write a comment first."
    elif len(form["content"]) > LIMITS["comment"]:
        errors["content"] = f"Keep it under {LIMITS['comment']} characters."
    if errors:
        return render_post(post_id, errors=errors, form=form, status=422)
    if not limiter.hit(("comment", client_key()), limit=10, window=600):
        errors["form"] = "Too many comments in a short time. Wait a bit and try again."
        return render_post(post_id, errors=errors, form=form, status=429)

    db = get_db()
    cur = db.execute(
        "INSERT INTO forum_comments (post_id, author, content, date) VALUES (?, ?, ?, ?)",
        (post_id, form["author"] or "Anonymous", form["content"], datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    return redirect(url_for("forum_post", post_id=post_id) + f"#comment-{cur.lastrowid}", code=303)


# --------------------------------------------------------------------------- api + meta

@app.route("/api/status")
def api_status():
    resp = jsonify(server_status())
    resp.headers["Cache-Control"] = "public, max-age=30"
    return resp


@app.route("/image/<path:filename>")
def legacy_image(filename):
    # Old pages and bookmarks referenced /image/...; icons now live in /static/img.
    return send_from_directory(STATIC_DIR / "img", filename)


@app.route("/site.webmanifest")
def webmanifest():
    manifest = {
        "name": "WarmBrew SMP",
        "short_name": "WarmBrew",
        "icons": [
            {"src": asset("img/android-chrome-192x192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": asset("img/android-chrome-512x512.png"), "sizes": "512x512", "type": "image/png"},
        ],
        "theme_color": "#17100c",
        "background_color": "#17100c",
        "display": "standalone",
        "start_url": "/",
    }
    return Response(json.dumps(manifest), mimetype="application/manifest+json")


@app.route("/robots.txt")
def robots():
    body = f"User-agent: *\nAllow: /\nSitemap: {site_url()}/sitemap.xml\n"
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    base = site_url()
    urls = [(f"{base}{path}", None) for path in ("/", "/play", "/guide", "/forum")]
    for row in get_db().execute("SELECT id, date FROM forum_posts ORDER BY id DESC LIMIT 1000"):
        urls.append((f"{base}/forum/post/{row['id']}", isodate(row["date"])))
    items = "".join(
        f"<url><loc>{xml_escape(loc)}</loc>{f'<lastmod>{mod}</lastmod>' if mod else ''}</url>"
        for loc, mod in urls
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'
    return Response(xml, mimetype="application/xml")


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(413)
@app.errorhandler(500)
def handle_error(err):
    code = getattr(err, "code", 500) or 500
    messages = {
        400: ("Something didn't add up", "Your session expired. Reload the page and try again."),
        404: ("Nothing out here", "This page doesn't exist, or someone griefed it."),
        405: ("Not like that", "That action isn't allowed on this page."),
        413: ("Too much text", "That was more than we can accept in one go. Shorten it and try again."),
        500: ("The server tripped", "Something broke on our side. Try again in a moment."),
    }
    title, message = messages.get(code, messages[500])
    return render_template("error.html", code=code, title=title, message=message), code


if __name__ == "__main__":
    port = int(os.environ.get("SERVER_PORT") or os.environ.get("PORT") or 25598)
    host = os.environ.get("HOST", "0.0.0.0")
    try:
        from waitress import serve
    except ImportError:
        print(f"waitress not installed; using Flask's built-in server on {host}:{port}")
        app.run(host=host, port=port, debug=False)
    else:
        print(f"WarmBrew SMP website on http://{host}:{port}")
        serve(app, host=host, port=port, threads=8)
