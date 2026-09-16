<div align="center">

<img src="static/img/android-chrome-192x192.png" width="96" height="96" alt="WarmBrew SMP logo">

# WarmBrew SMP: Website

**Pure vanilla anarchy survival for Minecraft Java 1.21.x – 26.x.**
No shops. No claims. No teleports. No rules.

`warmbrew.ankitgupta.com.np`

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/flask-3.x-000000?logo=flask&logoColor=white)
![Dependencies](https://img.shields.io/badge/frontend-zero%20dependencies-ffaa00)
![Pterodactyl](https://img.shields.io/badge/hosting-Pterodactyl-0e4688)

</div>

---

## Overview

The official website for the WarmBrew SMP Minecraft server. It's a single `app.py` Flask
application with plain HTML, CSS and JavaScript: no build step, no Node, no frontend
framework. Drop it on a Pterodactyl Python server and it runs.

| Page | What it does |
|---|---|
| `/` | Home. A scroll-driven hero, live server status, what's removed, what's installed, how to join, AI chat, modpack, latest forum threads |
| `/play` | Step-by-step join guide for premium and cracked accounts |
| `/guide` | What anarchy means here, command reference, account security, versions, plugins |
| `/forum` | Anonymous community forum with threads and replies |
| `/api/status` | Live server status as JSON (online, players, version, MOTD) |

## Highlights

- **Scroll-scrubbed hero.** The real pixel-art logo is sampled pixel by pixel into a canvas and comes apart as you scroll: "Sit back, relax & enjoy the survival vibe." becomes "Then trust no one." Every frame is a pure function of scroll position, so it runs backwards as cleanly as forwards.
- **Live server status.** `app.py` speaks the Minecraft Server List Ping protocol directly (no third-party API) and caches the result for 30 seconds.
- **Scroll-bound details.** Removed commands get struck through as you read them, and the join console types each step's command as you reach it.
- **Accessible.** Semantic HTML, keyboard focus states, skip link, AA contrast, and full `prefers-reduced-motion` support: animations collapse to their final, readable state.
- **Works without JavaScript.** Every page, every form and the forum all work with JS disabled.
- **Tiny.** No frontend dependencies. Pages are about 20 KB of HTML plus one stylesheet and one or two small scripts.

## Quick start (local)

```bash
git clone https://github.com/hyperdargo/WarmBrew-SMP.git
cd WarmBrew-SMP
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open <http://localhost:25598>.

## Deploying on Pterodactyl

1. Create a server with a **Python** egg (Python 3.10 or newer).
2. Upload the repository contents (or `git clone` it) into the server's root.
3. Make sure the egg installs `requirements.txt`. Most Python eggs have a "requirements file" or "Python packages" startup variable; otherwise run `pip install -r requirements.txt` once from the console.
4. Set the startup file to **`app.py`**.
5. Start the server. The app listens on the port Pterodactyl assigns through `SERVER_PORT` (falls back to `25598`).

> **Updating an existing install:** don't overwrite or delete `warmbrew.db`. It holds your forum posts.
> The schema is unchanged from earlier versions, so existing posts and comments carry over. The file is in `.gitignore`, so `git pull` won't touch it.

The app serves itself with [waitress](https://docs.pylonsproject.org/projects/waitress/), a production WSGI server, and never runs Flask in debug mode.

## Configuration

Everything is optional and set through environment variables (Pterodactyl startup variables work).

| Variable | Default | Purpose |
|---|---|---|
| `SERVER_PORT` / `PORT` | `25598` | Port to listen on |
| `SECRET_KEY` | auto-generated into `.secret_key` | Signs session cookies. Set it explicitly if you run several instances |
| `SITE_URL` | request host | Public URL, e.g. `https://your-domain`. Used for canonical links, Open Graph and the sitemap. **Recommended** |
| `MC_HOST` | `warmbrew.ankitgupta.com.np` | Minecraft server to ping for live status |
| `MC_PORT` | `25599` | Minecraft server port (from the domain's SRV record) |
| `DISCORD_URL` | *(empty)* | Discord invite link. The Discord link stays hidden until this is set |
| `DATABASE_PATH` | `./warmbrew.db` | SQLite file for the forum |
| `COOKIE_SECURE` | off | Set to `1` when the site is served over HTTPS |
| `TRUST_PROXY` | off | Set to `1` if the site sits behind one reverse proxy (Nginx, Cloudflare Tunnel…) so rate limits see real visitor IPs |

## Project structure

```
.
├── app.py               # Flask app: routes, forum, status ping, security, SEO
├── requirements.txt     # Flask + waitress
├── templates/
│   ├── base.html        # Shared layout, meta tags, header, footer
│   ├── index.html       # Home page
│   ├── play.html        # How to join
│   ├── guide.html       # Guide & commands
│   ├── forum.html       # Thread list + new thread form
│   ├── forum_post.html  # Thread + replies
│   └── error.html       # 400/404/405/413/500
├── static/
│   ├── css/site.css     # Design tokens and all styles
│   ├── js/site.js       # Copy-IP, header, form guard (every page)
│   ├── js/home.js       # Scroll-driven hero, strikes, console, live status
│   └── img/             # Logo and favicons
└── tests/test_app.py    # pytest suite
```

Server facts (versions, removed commands, plugin list, AI commands, links) live once, at the top of
`app.py`, so every page stays consistent. Edit them there.

## Security

- CSRF tokens on every form, `SameSite=Lax` + `HttpOnly` session cookies
- Strict Content Security Policy (no inline scripts), `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`
- Parameterised SQL everywhere; all user content is auto-escaped by Jinja
- Forum rate limits (3 threads / 10 min, 10 replies / 10 min per IP), length limits, 64 KB request cap, and a honeypot field for bots
- Debug mode is never enabled; no secrets live in the repository

**Moderation:** the forum is anonymous and there is no admin panel yet. To remove a post, stop the site and run:

```bash
sqlite3 warmbrew.db "DELETE FROM forum_comments WHERE post_id = 42; DELETE FROM forum_posts WHERE id = 42;"
```

## Testing

```bash
pip install pytest
python -m pytest tests
```

Covers every page, the 404 page, live status parsing (online and offline), CSRF enforcement, XSS escaping,
validation errors, rate limiting, the honeypot and the request size limit.

## Related projects

- [DTEmpire AI Chat](https://github.com/hyperdargo/DTEmpireAiPlugin): the private in-game AI plugin used on the server (MIT)
- [DTEmpire Optimized](https://modrinth.com/modpack/dtempire-optimized): a client-side Fabric performance modpack

---

<div align="center">
<sub>Not affiliated with Mojang or Microsoft. Minecraft is a trademark of Mojang Synergies AB.</sub>
</div>
