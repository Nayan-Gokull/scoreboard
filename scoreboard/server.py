#!/usr/bin/env python3
"""
Scoreboard Server — with auth, roles, XML broadcast endpoint, and SSE streaming.

Run with:
    python3 server.py

Environment variables:
    PORT           - HTTP port (default 8765; Render sets this automatically)
    DATA_DIR       - where state.json and media/ live (default: next to server.py)
    COOKIE_SECRET  - secret used to sign session cookies (default: auto-generated once)

Open:
    http://localhost:8765/login      ← start here
    http://localhost:8765/display    ← public live feed
    http://localhost:8765/xml        ← broadcast XML feed
"""

import base64
import csv
import hashlib
import hmac
import io
import json
import mimetypes
import os
import queue
import re
import secrets
import shutil
import socket
import sys
import threading
import time
import urllib.parse
import xml.sax.saxutils as xml_esc
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
#  PATHS & CONFIG
# ═══════════════════════════════════════════════════════════════════════════
BASE      = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
STATIC    = Path(__file__).parent / "static"
MEDIA     = BASE / "media"
STATE     = BASE / "state.json"
USERS     = BASE / "users.json"
CONFIG    = BASE / "config.json"
PLAYERS   = BASE / "players.json"
GAMES_DIR = BASE / "games"
FIXTURES  = BASE / "fixtures.json"

def get_all_local_ips():
    """Return all non-loopback IPv4 addresses on this machine."""
    ips = []
    # Method 1: enumerate via hostname resolution
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    # Method 2: outbound-route trick (catches adapters hostname lookup misses)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and ip not in ips:
            ips.append(ip)
    except Exception:
        pass
    return [ip for ip in ips if ip != "127.0.0.1" and not ip.startswith("169.254")]

for sub in ["logos", "ads", "slots", "sponsors", "presented_by", "cues", "selfies"]:
    (MEDIA / sub).mkdir(parents=True, exist_ok=True)
(MEDIA / "selfies" / "pending").mkdir(parents=True, exist_ok=True)
GAMES_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════
#  DEFAULT STATE
# ═══════════════════════════════════════════════════════════════════════════
DEFAULT_STATE = {
    # identity
    "id": "", "createdAt": 0, "finalizedAt": 0,
    "sport": "soccer",
    "homeTeam": "Team 1", "awayTeam": "Team 2",
    "leagueName": "UNIVERSITY LEAGUE",
    "matchday": "", "season": "",
    "homeScore": 0, "awayScore": 0,
    "period": 0, "clock": "00:00", "clockRunning": False, "clockAnchorWall": 0,
    "gameStatus": "SETUP",
    "gameDate": "—", "gameLocation": "—", "kickoff": "",
    "homeRecord": "—", "awayRecord": "—",
    "homeLogo": "", "awayLogo": "",
    "adSlot1": "", "adSlot2": "", "adSlot3": "",
    "presentedByLogo": "", "presentedByText": "PRESENTED BY",
    "sponsors": [],
    "announcement": "", "annSeq": 0,
    "teamAColor": "#e8272f", "teamBColor": "#1565c0",
    "possession": "none", "stats": {}, "extras": {},
    "events": [],
    "playerStats": {},
    "lowerThird": None, "celebration": None,
    "lBug": {"logo": "", "position": "tr", "visible": False},
    "celebSponsor": "", "announcementLogo": "",
    "papare": {"logo": "", "text": "PAPARE", "visible": True},
    "lCard": {"visible": False, "url": ""},
    "videoSource": "", "videoPlaying": False, "showScoreBug": False,
    "adSchedule": [],
    "adScheduleActive": False, "adScheduleCurrent": -1, "adScheduleCmd": None,
    "vadSeq": 0, "vadCmd": None, "vadType": "image",
    "vadDuration": 15, "vadUrl": "",
    "cues": [], "cueIndex": -1,
    "qrOverlay": {"active": False, "url": "", "headline": "", "subtext": "", "label": "", "seq": 0},
    "poll": {"active": False, "question": "", "options": [], "votes": {}, "seq": 0},
    "pollResultsOverlay": {"active": False, "seq": 0},
    "selfieWall": {"active": False, "qrUrl": "", "seq": 0, "requireApproval": False, "sponsorLogo": ""},
    "gameCode": "", "requireGameCode": True,
}

def load_state():
    try:
        if STATE.exists():
            with open(STATE) as f:
                return {**DEFAULT_STATE, **json.load(f)}
    except Exception as e:
        print(f"[state] load error: {e}")
    return dict(DEFAULT_STATE)

_state_lock = threading.Lock()

def save_state(data):
    with _state_lock:
        for attempt in range(4):
            try:
                with open(STATE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return True
            except OSError as e:
                if attempt < 3:
                    time.sleep(0.05 * (attempt + 1))
                else:
                    print(f"[state] save error: {e}")
                    return False

if not STATE.exists():
    save_state(DEFAULT_STATE)

# ═══════════════════════════════════════════════════════════════════════════
#  CONFIG (general settings — broadcast token, etc.)
# ═══════════════════════════════════════════════════════════════════════════
DEFAULT_CONFIG = {
    "broadcastToken": "",  # empty = XML endpoint is public; set a string to require ?token=...
    "requireHttps": False,  # set True in production
}

def load_config():
    try:
        if CONFIG.exists():
            with open(CONFIG) as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    try:
        with open(CONFIG, "w") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception:
        return False

if not CONFIG.exists():
    save_config(DEFAULT_CONFIG)

# ═══════════════════════════════════════════════════════════════════════════
#  PLAYER ROSTER
# ═══════════════════════════════════════════════════════════════════════════
DEFAULT_PLAYERS = {"home": [], "away": []}

def load_players():
    try:
        if PLAYERS.exists():
            with open(PLAYERS) as f:
                return json.load(f)
    except Exception as e:
        print(f"[players] load error: {e}")
    return {"home": [], "away": []}

def save_players(data):
    try:
        with open(PLAYERS, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"[players] save error: {e}")
        return False

def parse_players_csv(content: str) -> dict:
    """Parse CSV text into {home:[...], away:[...]} roster."""
    result = {"home": [], "away": []}
    try:
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            side = row.get("side", "home").lower()
            if side not in ("home", "away"):
                side = "home"
            name = row.get("name", row.get("player", ""))
            if not name:
                continue
            result[side].append({
                "number": row.get("number", row.get("no", row.get("#", "?"))),
                "name": name,
                "position": row.get("position", row.get("pos", "—")),
            })
    except Exception as e:
        print(f"[players] csv parse error: {e}")
    return result

if not PLAYERS.exists():
    save_players(DEFAULT_PLAYERS)

# ═══════════════════════════════════════════════════════════════════════════
#  FIXTURES  (scheduled / upcoming games)
# ═══════════════════════════════════════════════════════════════════════════
def load_fixtures():
    try:
        if FIXTURES.exists():
            with open(FIXTURES) as f:
                return json.load(f)
    except Exception as e:
        print(f"[fixtures] load error: {e}")
    return []

_fixtures_lock = threading.Lock()

def save_fixtures(data):
    with _fixtures_lock:
        for attempt in range(4):
            try:
                with open(FIXTURES, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return True
            except OSError as e:
                if attempt < 3:
                    time.sleep(0.05 * (attempt + 1))
                else:
                    print(f"[fixtures] save error: {e}")
                    return False

# ═══════════════════════════════════════════════════════════════════════════
#  GAME ARCHIVE  (completed games)
# ═══════════════════════════════════════════════════════════════════════════
def list_games():
    """Return lightweight index of all archived games, newest first."""
    games = []
    for f in GAMES_DIR.glob("*.json"):
        try:
            with open(f) as fp:
                g = json.load(fp)
            games.append({
                "id":          g.get("id", f.stem),
                "leagueName":  g.get("leagueName", ""),
                "matchday":    g.get("matchday", ""),
                "season":      g.get("season", ""),
                "homeTeam":    g.get("homeTeam", ""),
                "awayTeam":    g.get("awayTeam", ""),
                "homeScore":   g.get("homeScore", 0),
                "awayScore":   g.get("awayScore", 0),
                "sport":       g.get("sport", "soccer"),
                "date":        g.get("gameDate", ""),
                "venue":       g.get("gameLocation", ""),
                "finalizedAt": g.get("finalizedAt", 0),
                "events":      g.get("events", []),
                "playerStats": g.get("playerStats", {}),
                "stats":       g.get("stats", {}),
            })
        except Exception:
            pass
    return sorted(games, key=lambda x: x.get("finalizedAt", 0), reverse=True)

# ═══════════════════════════════════════════════════════════════════════════
#  PASSWORDS & USERS
# ═══════════════════════════════════════════════════════════════════════════
PBKDF2_ITER = 120_000

def hash_password(pw: str, salt: bytes = None):
    """Return 'base64salt$base64hash' string."""
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, PBKDF2_ITER)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"

def verify_password(pw: str, stored: str) -> bool:
    try:
        salt_b64, hash_b64 = stored.split("$", 1)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        check = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, PBKDF2_ITER)
        return hmac.compare_digest(expected, check)
    except Exception:
        return False

DEFAULT_USERS = {
    "admin":    {"password": hash_password("admin"),    "role": "admin",    "name": "Administrator"},
    "operator": {"password": hash_password("operator"), "role": "operator", "name": "Match Operator"},
    "scorer":   {"password": hash_password("scorer"),   "role": "scorer",   "name": "Stats Scorer"},
}

def load_users():
    try:
        if USERS.exists():
            with open(USERS) as f:
                return json.load(f)
    except Exception as e:
        print(f"[users] load error: {e}")
    return None

def save_users(users):
    try:
        with open(USERS, "w") as f:
            json.dump(users, f, indent=2)
        return True
    except Exception:
        return False

users = load_users()
if not users:
    print("[users] creating default users.json with admin/admin, operator/operator, scorer/scorer")
    print("[users] ⚠️  CHANGE THESE PASSWORDS IN users.json BEFORE DEPLOYMENT!")
    users = DEFAULT_USERS
    save_users(users)

# ═══════════════════════════════════════════════════════════════════════════
#  SESSION / COOKIE HANDLING
# ═══════════════════════════════════════════════════════════════════════════
COOKIE_SECRET = os.environ.get("COOKIE_SECRET") or ""
if not COOKIE_SECRET:
    secret_file = BASE / ".cookie_secret"
    if secret_file.exists():
        COOKIE_SECRET = secret_file.read_text().strip()
    else:
        COOKIE_SECRET = secrets.token_urlsafe(48)
        secret_file.write_text(COOKIE_SECRET)
        print(f"[auth] generated new cookie secret → {secret_file}")

COOKIE_NAME = "sb_session"
SESSION_TTL = 60 * 60 * 12  # 12 hours

def make_session_token(username: str) -> str:
    """Sign a session token with HMAC — self-contained, no server-side storage needed."""
    payload = {"u": username, "exp": int(time.time()) + SESSION_TTL}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig = hmac.new(COOKIE_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"

def verify_session_token(token: str):
    """Return user dict if valid, None if not."""
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(COOKIE_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        padding = "=" * ((4 - len(body) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + padding))
        if payload.get("exp", 0) < time.time():
            return None
        username = payload.get("u")
        if username not in users:
            return None
        u = users[username]
        return {"username": username, "role": u["role"], "name": u.get("name", username)}
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  LOGIN RATE LIMITING  (in-memory, per remote IP)
# ═══════════════════════════════════════════════════════════════════════════
_login_failures: dict = {}   # ip → [timestamp, ...]
_login_rl_lock  = threading.Lock()
LOGIN_MAX_FAILURES = 5
LOGIN_FAILURE_WINDOW = 300   # 5 minutes
LOGIN_LOCKOUT_TTL    = 900   # 15 minutes

def _rl_check(ip: str):
    """Return (allowed, seconds_until_unlock)."""
    now = time.time()
    with _login_rl_lock:
        ts = [t for t in _login_failures.get(ip, []) if now - t < LOGIN_LOCKOUT_TTL]
        _login_failures[ip] = ts
        recent = [t for t in ts if now - t < LOGIN_FAILURE_WINDOW]
        if len(recent) >= LOGIN_MAX_FAILURES:
            wait = int(min(ts) + LOGIN_LOCKOUT_TTL - now) + 1
            return False, max(1, wait)
        return True, 0

def _rl_fail(ip: str):
    with _login_rl_lock:
        _login_failures.setdefault(ip, []).append(time.time())

def _rl_clear(ip: str):
    with _login_rl_lock:
        _login_failures.pop(ip, None)

# ═══════════════════════════════════════════════════════════════════════════
#  SSE (SERVER-SENT EVENTS) — real-time state push to display + dashboards
# ═══════════════════════════════════════════════════════════════════════════
sse_clients = []
sse_lock = threading.Lock()

def sse_broadcast_state():
    """Push current state.json to all connected SSE clients."""
    try:
        with open(STATE) as f:
            payload = f.read()
    except Exception:
        return
    msg = f"data: {payload}\n\n".encode("utf-8")
    with sse_lock:
        dead = []
        for q_obj in sse_clients:
            try:
                q_obj.put_nowait(msg)
            except Exception:
                dead.append(q_obj)
        for d in dead:
            if d in sse_clients:
                sse_clients.remove(d)

# ═══════════════════════════════════════════════════════════════════════════
#  XML ENDPOINT BUILDER
# ═══════════════════════════════════════════════════════════════════════════
SPORT_PERIODS = {
    "soccer": ["1ST HALF", "2ND HALF", "EXTRA TIME 1", "EXTRA TIME 2", "PENALTIES"],
    "basketball": ["Q1", "Q2", "Q3", "Q4", "OT"],
    "rugby": ["1ST HALF", "2ND HALF", "EXTRA TIME 1", "EXTRA TIME 2"],
}
SPORT_STAT_LABELS = {
    "soccer": {"possession": "Possession %", "shots": "Shots", "corners": "Corners", "fouls": "Fouls"},
    "basketball": {"hFouls": "Home Fouls", "aFouls": "Away Fouls", "hTO": "Home Timeouts", "aTO": "Away Timeouts"},
    "rugby": {"tries": "Tries", "conversions": "Conversions", "penalties": "Penalties", "yellowCards": "Yellow Cards"},
}

def esc(v):
    return xml_esc.escape(str(v) if v is not None else "")

def esc_attr(v):
    return xml_esc.quoteattr(str(v) if v is not None else "")

def state_to_xml(s: dict) -> str:
    sport = s.get("sport", "soccer")
    periods = SPORT_PERIODS.get(sport, SPORT_PERIODS["soccer"])
    period_idx = max(0, min(s.get("period", 0), len(periods) - 1))
    period_label = periods[period_idx]
    stat_labels = SPORT_STAT_LABELS.get(sport, {})

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<scoreboard updated={esc_attr(now_iso)} sport={esc_attr(sport)}>',
        f'  <league>{esc(s.get("leagueName", ""))}</league>',
        f'  <status>{esc(s.get("gameStatus", ""))}</status>',
        f'  <period index="{period_idx}" label={esc_attr(period_label)}/>',
        f'  <clock running="{"true" if s.get("clockRunning") else "false"}">{esc(s.get("clock", "00:00"))}</clock>',
        f'  <date>{esc(s.get("gameDate", ""))}</date>',
        f'  <venue>{esc(s.get("gameLocation", ""))}</venue>',
        '  <teams>',
        f'    <home name={esc_attr(s.get("homeTeam",""))} score="{s.get("homeScore",0)}" '
          f'record={esc_attr(s.get("homeRecord",""))} color={esc_attr(s.get("teamAColor",""))} '
          f'possession="{"true" if s.get("possession")=="home" else "false"}"/>',
        f'    <away name={esc_attr(s.get("awayTeam",""))} score="{s.get("awayScore",0)}" '
          f'record={esc_attr(s.get("awayRecord",""))} color={esc_attr(s.get("teamBColor",""))} '
          f'possession="{"true" if s.get("possession")=="away" else "false"}"/>',
        '  </teams>',
    ]

    # Stats
    stats = s.get("stats") or {}
    if stats:
        lines.append('  <stats>')
        for k, v in stats.items():
            label = stat_labels.get(k, k)
            lines.append(f'    <stat key={esc_attr(k)} label={esc_attr(label)}>{esc(v)}</stat>')
        lines.append('  </stats>')

    # Events
    events = s.get("events") or []
    lines.append(f'  <events count="{len(events)}">')
    for ev in events:
        lines.append(
            f'    <event id="{ev.get("id","")}" time={esc_attr(ev.get("time",""))} '
            f'type={esc_attr(ev.get("type",""))} player={esc_attr(ev.get("player",""))} '
            f'team={esc_attr(ev.get("team",""))} side={esc_attr(ev.get("side",""))} '
            f'score={esc_attr(ev.get("score",""))}/>'
        )
    lines.append('  </events>')

    lines.append('</scoreboard>')
    return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════════════════
#  ROLE PERMISSIONS
# ═══════════════════════════════════════════════════════════════════════════
# Admin can do anything; operator runs matches; scorer only edits scores + events
ROLE_PERMS = {
    "admin":    {"state_write": True,  "state_read": True, "upload": True,  "delete": True,
                 "scorer_only": False},
    "operator": {"state_write": True,  "state_read": True, "upload": True,  "delete": True,
                 "scorer_only": False},
    "scorer":   {"state_write": True,  "state_read": True, "upload": False, "delete": False,
                 "scorer_only": True},  # scorer can only modify specific fields
}

# Fields a scorer is allowed to change via /state — everything else is preserved
SCORER_ALLOWED_FIELDS = {
    "homeScore", "awayScore", "events", "possession",
    "stats", "extras", "lowerThird", "celebration",
    "announcement", "annSeq", "playerStats",
}

# ═══════════════════════════════════════════════════════════════════════════
#  HTTP HANDLER
# ═══════════════════════════════════════════════════════════════════════════
class Handler(BaseHTTPRequestHandler):
    # suppress default access log spam
    def log_message(self, fmt, *args):
        pass

    # ── HELPERS ──
    def _get_cookies(self):
        raw = self.headers.get("Cookie") or ""
        out = {}
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                out[k] = v
        return out

    def _current_user(self):
        c = self._get_cookies()
        tok = c.get(COOKIE_NAME, "")
        if not tok:
            return None
        return verify_session_token(tok)

    def _send(self, code, body=b"", content_type="text/plain", extra_headers=None, no_cache=False):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if no_cache:
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
        # CORS for XML polling convenience
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, data, code=200, extra_headers=None):
        self._send(code, json.dumps(data).encode(), "application/json",
                   extra_headers=extra_headers, no_cache=True)

    def _error(self, msg, code=400):
        self._send_json({"ok": False, "error": msg}, code=code)

    def _redirect(self, location, extra_headers=None):
        h = {"Location": location}
        if extra_headers:
            h.update(extra_headers)
        self.send_response(302)
        for k, v in h.items():
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()


    def _require_login(self):
        user = self._current_user()
        if not user:
            # If it looks like an API request, return JSON; else redirect
            accept = self.headers.get("Accept", "")
            if "application/json" in accept or self.path.startswith("/api/") or self.path == "/state":
                self._error("Unauthorized", 401)
            else:
                self._redirect("/login")
            return None
        return user

    def _require_role(self, *allowed_roles):
        user = self._require_login()
        if not user:
            return None
        if user["role"] not in allowed_roles:
            self._error("Forbidden: role " + user["role"], 403)
            return None
        return user

    # ── DISPATCH ──
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"

        # ── Public routes ──
        if path == "/login":
            return self._serve_static("login.html")
        if path == "/display":
            return self._serve_static("display.html")
        if path == "/poll":
            return self._serve_static("poll.html")
        if path == "/selfie":
            return self._serve_static("selfie.html")
        if path == "/api/selfie/list":
            selfie_dir = MEDIA / "selfies"
            files = sorted(selfie_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
            urls = [f"/media/selfies/{p.name}" for p in files[:60]]
            return self._send_json({"urls": urls, "count": len(files)})
        if path == "/api/selfie/pending":
            user = self._require_role("admin", "operator")
            if not user: return
            pending_dir = MEDIA / "selfies" / "pending"
            files = sorted(pending_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=False)
            urls = [f"/media/selfies/pending/{p.name}" for p in files]
            return self._send_json({"urls": urls, "count": len(files)})
        if path == "/api/localip":
            if not self._current_user():
                return self._error("Unauthorized", 401)
            port = self.server.server_address[1]
            ips = get_all_local_ips()
            return self._send_json({"ips": ips, "port": port})
        if path == "/api/poll/data":
            st = load_state()
            p = st.get("poll", {})
            return self._send_json({
                "active": p.get("active", False),
                "question": p.get("question", ""),
                "options": p.get("options", []),
                "votes": p.get("votes", {}),
                "seq": p.get("seq", 0),
            })
        if path in ("/xml", "/scoreboard.xml", "/xml.xml"):
            return self._handle_xml()
        if path == "/events":
            return self._handle_sse(None)
        if path == "/api/me":
            user = self._current_user()
            if not user:
                return self._send_json({"loggedIn": False}, code=200)
            return self._send_json({"loggedIn": True, **user})
        if path.startswith("/media/"):
            return self._serve_media(path)

        # ── Authed routes ──
        if path == "/":
            user = self._current_user()
            if not user:
                return self._redirect("/login")
            return self._redirect({"admin": "/dashboard", "operator": "/dashboard", "scorer": "/scorer"}.get(user["role"], "/login"))

        if path == "/dashboard":
            user = self._require_login()
            if not user: return
            if user["role"] == "scorer":
                return self._redirect("/scorer")
            return self._serve_static("dashboard.html")

        if path == "/scorer":
            user = self._require_login()
            if not user: return
            return self._serve_static("scorer.html")

        if path == "/state":
            return self._send_json(load_state())

        if path == "/api/media-list":
            user = self._require_role("admin", "operator")
            if not user: return
            return self._send_json(self._build_media_list())

        if path == "/api/config":
            user = self._require_role("admin")
            if not user: return
            return self._send_json(load_config())

        if path == "/api/players":
            return self._send_json(load_players())

        # ── Game lifecycle ──
        if path == "/setup":
            user = self._require_role("admin", "operator")
            if not user: return
            return self._serve_static("setup.html")

        if path == "/api/fixtures":
            user = self._require_login()
            if not user: return
            return self._send_json(load_fixtures())

        if path == "/api/games":
            user = self._require_login()
            if not user: return
            return self._send_json(list_games())

        m = re.match(r'^/api/games/([\w\-]+)$', path)
        if m:
            user = self._require_login()
            if not user: return
            gf = GAMES_DIR / f"{m.group(1)}.json"
            if not gf.exists():
                return self._error("Game not found", 404)
            with open(gf) as f:
                return self._send_json(json.load(f))

        return self._send(404, "Not found", no_cache=True)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/api/login":
            return self._handle_login()
        if path == "/api/logout":
            return self._handle_logout()
        if path == "/api/poll/vote":
            return self._handle_poll_vote()
        if path == "/api/selfie/upload":
            return self._handle_selfie_upload()

        # Everything below needs auth
        user = self._current_user()
        if not user:
            return self._error("Unauthorized", 401)

        if path == "/state":
            return self._handle_state_post(user)
        if path.startswith("/upload/"):
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_upload(path)
        if path == "/api/config":
            if user["role"] != "admin":
                return self._error("Admin only", 403)
            return self._handle_config_post()
        if path == "/api/users":
            if user["role"] != "admin":
                return self._error("Admin only", 403)
            return self._handle_users_post()

        if path == "/api/players":
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_players_post()

        if path == "/api/players/upload":
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_players_upload()

        # ── Game lifecycle ──
        if path == "/api/games/new":
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_new_game()

        if path == "/api/games/finalize":
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_finalize_game()

        if path == "/api/fixtures":
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_fixtures_post()

        m = re.match(r'^/api/fixtures/([\w\-]+)/load$', path)
        if m:
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_fixture_load(m.group(1))

        if path == "/api/poll/reset":
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_poll_reset()

        if path == "/api/selfie/clear":
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_selfie_clear()

        m = re.match(r'^/api/selfie/approve/([\w.\-]+)$', path)
        if m:
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_selfie_approve(m.group(1))

        m = re.match(r'^/api/selfie/reject/([\w.\-]+)$', path)
        if m:
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_selfie_reject(m.group(1))

        return self._error("Unknown route", 404)

    def _handle_poll_vote(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            opt_idx = data.get("option")
            if not isinstance(opt_idx, int) or opt_idx < 0:
                return self._error("Bad option", 400)
        except Exception:
            return self._error("Bad request", 400)
        st = load_state()
        p = st.get("poll", {})
        if not p.get("active"):
            return self._error("Poll not active", 403)
        opts = p.get("options", [])
        if opt_idx >= len(opts):
            return self._error("Invalid option", 400)
        votes = dict(p.get("votes", {}))
        idx = str(opt_idx)
        votes[idx] = votes.get(idx, 0) + 1
        p["votes"] = votes
        st["poll"] = p
        save_state(st)
        sse_broadcast_state()
        return self._send_json({"ok": True, "votes": votes})

    def _handle_poll_reset(self):
        st = load_state()
        p = st.get("poll", {})
        p["votes"] = {}
        st["poll"] = p
        save_state(st)
        sse_broadcast_state()
        return self._send_json({"ok": True})

    def _handle_selfie_upload(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 4 * 1024 * 1024:
                return self._error("File too large", 413)
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            img_data = data.get("image", "")
            if not img_data:
                return self._error("No image", 400)
            if "," in img_data:
                img_data = img_data.split(",", 1)[1]
            img_bytes = base64.b64decode(img_data)
        except Exception:
            return self._error("Bad request", 400)
        st = load_state()
        require_approval = st.get("selfieWall", {}).get("requireApproval", False)
        selfie_dir = MEDIA / "selfies" / "pending" if require_approval else MEDIA / "selfies"
        selfie_dir.mkdir(parents=True, exist_ok=True)
        fname = f"selfie_{int(time.time() * 1000)}_{secrets.token_hex(4)}.jpg"
        dest = selfie_dir / fname
        try:
            dest.write_bytes(img_bytes)
            if require_approval:
                return self._send_json({"ok": True, "pending": True})
            sse_broadcast_state()
            return self._send_json({"ok": True, "pending": False})
        except Exception as e:
            return self._error(str(e), 500)

    def _handle_selfie_approve(self, fname):
        if not re.match(r'^[\w.\-]+$', fname):
            return self._error("Invalid filename", 400)
        src = MEDIA / "selfies" / "pending" / fname
        dst = MEDIA / "selfies" / fname
        if not src.exists():
            return self._error("Not found", 404)
        try:
            src.rename(dst)
            sse_broadcast_state()
            return self._send_json({"ok": True})
        except Exception as e:
            return self._error(str(e), 500)

    def _handle_selfie_reject(self, fname):
        if not re.match(r'^[\w.\-]+$', fname):
            return self._error("Invalid filename", 400)
        src = MEDIA / "selfies" / "pending" / fname
        if not src.exists():
            return self._error("Not found", 404)
        try:
            src.unlink()
            return self._send_json({"ok": True})
        except Exception as e:
            return self._error(str(e), 500)

    def _handle_selfie_delete(self, fname):
        if not re.match(r'^[\w.\-]+$', fname):
            return self._error("Invalid filename", 400)
        target = MEDIA / "selfies" / fname
        try:
            target.resolve().relative_to((MEDIA / "selfies").resolve())
        except ValueError:
            return self._error("Invalid path", 400)
        if not target.exists() or not target.is_file():
            return self._error("Not found", 404)
        try:
            target.unlink()
            sse_broadcast_state()
            return self._send_json({"ok": True})
        except Exception as e:
            return self._error(str(e), 500)

    def _handle_selfie_clear(self):
        selfie_dir = MEDIA / "selfies"
        removed = 0
        try:
            for f in selfie_dir.glob("*.jpg"):
                f.unlink(missing_ok=True)
                removed += 1
            for f in (selfie_dir / "pending").glob("*.jpg"):
                f.unlink(missing_ok=True)
                removed += 1
        except Exception as e:
            return self._error(str(e), 500)
        sse_broadcast_state()
        return self._send_json({"ok": True, "removed": removed})

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        user = self._current_user()
        if not user:
            return self._error("Unauthorized", 401)
        if path.startswith("/media/"):
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_delete(path)
        m = re.match(r'^/api/games/([\w\-]+)$', path)
        if m:
            if user["role"] != "admin":
                return self._error("Forbidden", 403)
            return self._handle_delete_game(m.group(1))
        m = re.match(r'^/api/fixtures/([\w\-]+)$', path)
        if m:
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            fixtures = load_fixtures()
            save_fixtures([f for f in fixtures if f.get("id") != m.group(1)])
            return self._send_json({"ok": True})
        m = re.match(r'^/api/selfie/([\w.\-]+)$', path)
        if m:
            if user["role"] not in ("admin", "operator"):
                return self._error("Forbidden", 403)
            return self._handle_selfie_delete(m.group(1))
        return self._error("Unknown route", 404)

    # ═══ HANDLERS ═══════════════════════════════════════════════════════════
    def _handle_login(self):
        try:
            ip = self.client_address[0]
            allowed, wait = _rl_check(ip)
            if not allowed:
                mins = (wait // 60) + 1
                return self._error(f"Too many failed attempts. Try again in {mins} minute{'s' if mins != 1 else ''}.", 429)
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            uname = (data.get("username") or "").strip().lower()
            pw = data.get("password") or ""
            u = users.get(uname)
            if not u or not verify_password(pw, u["password"]):
                _rl_fail(ip)
                time.sleep(0.3)
                return self._error("Invalid username or password", 401)
            _rl_clear(ip)
            token = make_session_token(uname)
            cookie = f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}"
            cfg = load_config()
            if cfg.get("requireHttps"):
                cookie += "; Secure"
            self._send_json(
                {"ok": True, "role": u["role"], "name": u.get("name", uname), "username": uname},
                extra_headers={"Set-Cookie": cookie},
            )
        except Exception as e:
            self._error(str(e), 500)

    def _handle_logout(self):
        cookie = f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
        self._send_json({"ok": True}, extra_headers={"Set-Cookie": cookie})

    def _handle_state_post(self, user):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            incoming = json.loads(raw)

            # Scorer is restricted to a whitelist of fields
            if user["role"] == "scorer":
                current = load_state()
                for k, v in incoming.items():
                    if k in SCORER_ALLOWED_FIELDS:
                        current[k] = v
                save_state(current)
            else:
                # Protect poll votes — they are written only by /api/poll/vote
                # and must not be overwritten when the dashboard posts its state
                # (which may carry a stale votes dict from before audience voted).
                current = load_state()
                if "poll" in incoming and isinstance(incoming["poll"], dict):
                    incoming["poll"]["votes"] = current.get("poll", {}).get("votes", {})
                save_state(incoming)

            sse_broadcast_state()
            self._send_json({"ok": True})
        except Exception as e:
            self._error(str(e), 500)

    def _handle_upload(self, path):
        parts = path.strip("/").split("/", 2)
        if len(parts) < 3:
            return self._error("Bad upload path")
        _, category, filename = parts
        filename = re.sub(r"[^a-zA-Z0-9._\-]", "_", filename)
        # prevent category path traversal
        category = re.sub(r"[^a-zA-Z0-9_\-]", "", category)
        if not category:
            return self._error("Bad category")
        dest_dir = MEDIA / category
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        try:
            length = int(self.headers.get("Content-Length", 0))
            CHUNK = 65536
            written = 0
            with open(dest, "wb") as f:
                while written < length:
                    chunk = self.rfile.read(min(CHUNK, length - written))
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
            url = f"/media/{category}/{filename}"
            self._send_json({"ok": True, "url": url, "size": written})
            print(f"[upload] {url} ({written//1024}KB)")
        except Exception as e:
            self._error(str(e), 500)

    def _handle_delete(self, path):
        rel = path[len("/media/"):]
        target = MEDIA / rel
        try:
            target.resolve().relative_to(MEDIA.resolve())
        except ValueError:
            return self._error("Invalid path", 400)
        if not target.exists() or not target.is_file():
            return self._error("Not found", 404)
        try:
            target.unlink()
            self._send_json({"ok": True})
        except Exception as e:
            self._error(str(e), 500)

    def _handle_config_post(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            cfg = load_config()
            cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
            save_config(cfg)
            self._send_json({"ok": True, "config": cfg})
        except Exception as e:
            self._error(str(e), 500)

    def _handle_users_post(self):
        """Admin-only: create/update/delete users."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            action = data.get("action")
            uname = (data.get("username") or "").strip().lower()
            if not uname:
                return self._error("Username required")
            if action == "delete":
                if uname == "admin":
                    return self._error("Cannot delete admin account")
                users.pop(uname, None)
                save_users(users)
                return self._send_json({"ok": True})
            if action in ("create", "update"):
                role = data.get("role", "scorer")
                if role not in ROLE_PERMS:
                    return self._error("Invalid role")
                name = data.get("name", uname)
                pw = data.get("password", "")
                existing = users.get(uname)
                if action == "create" and existing:
                    return self._error("User already exists")
                if action == "create" and not pw:
                    return self._error("Password required")
                record = existing or {}
                record["role"] = role
                record["name"] = name
                if pw:
                    record["password"] = hash_password(pw)
                users[uname] = record
                save_users(users)
                return self._send_json({"ok": True, "user": {"username": uname, "role": role, "name": name}})
            return self._error("Unknown action")
        except Exception as e:
            self._error(str(e), 500)

    def _handle_xml(self):
        cfg = load_config()
        token = cfg.get("broadcastToken", "")
        if token:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            supplied = (qs.get("token") or [""])[0]
            if supplied != token:
                return self._error("Token required or invalid", 401)
        try:
            s = load_state()
            xml_body = state_to_xml(s)
            self._send(200, xml_body, "application/xml; charset=utf-8", no_cache=True)
        except Exception as e:
            self._error(str(e), 500)

    def _handle_sse(self, user):
        """Server-Sent Events stream — one per connected client."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")  # disable nginx buffering
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q_obj = queue.Queue(maxsize=50)
        with sse_lock:
            sse_clients.append(q_obj)

        # Windows raises ConnectionAbortedError (WinError 10053) instead of
        # BrokenPipeError when the browser closes an SSE connection.
        _BROKEN = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)

        try:
            # Send initial state immediately
            try:
                with open(STATE) as f:
                    initial = f.read()
                self.wfile.write(f"data: {initial}\n\n".encode())
                self.wfile.flush()
            except _BROKEN:
                return  # client already gone before first write
            except Exception:
                pass
            # Heartbeat + live pushes
            while True:
                try:
                    msg = q_obj.get(timeout=15)
                    self.wfile.write(msg)
                    self.wfile.flush()
                except queue.Empty:
                    # heartbeat keeps connection alive through proxies
                    try:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    except _BROKEN:
                        break
                    except Exception:
                        break
                except _BROKEN:
                    break
        finally:
            with sse_lock:
                if q_obj in sse_clients:
                    sse_clients.remove(q_obj)

    def _serve_static(self, filename):
        path = STATIC / filename
        if not path.exists():
            return self._send(404, f"Not found: {filename}")
        with open(path, "rb") as f:
            body = f.read()
        self._send(200, body, "text/html; charset=utf-8", no_cache=True)

    def _serve_media(self, url_path):
        rel = url_path[len("/media/"):]
        file_path = MEDIA / rel
        if not file_path.exists() or not file_path.is_file():
            return self._send(404, "Not found")
        try:
            file_path.resolve().relative_to(MEDIA.resolve())
        except ValueError:
            return self._send(404, "Not found")

        mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        size = file_path.stat().st_size
        range_header = self.headers.get("Range")

        if range_header:
            m = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if m:
                start = int(m.group(1)) if m.group(1) else 0
                end = int(m.group(2)) if m.group(2) else size - 1
                end = min(end, size - 1)
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        remaining -= len(chunk)
                return

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(file_path, "rb") as f:
            try:
                shutil.copyfileobj(f, self.wfile)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _build_media_list(self):
        result = {}
        for cat in MEDIA.iterdir():
            if cat.is_dir():
                result[cat.name] = [
                    {"name": f.name, "url": f"/media/{cat.name}/{f.name}", "size": f.stat().st_size}
                    for f in sorted(cat.iterdir()) if f.is_file()
                ]
        return result


    def _handle_new_game(self):
        """Create a fresh game state from setup wizard data."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            new_state = dict(DEFAULT_STATE)
            new_state.update({
                "homeScore": 0, "awayScore": 0,
                "period": 0, "clock": "00:00", "clockRunning": False, "clockAnchorWall": 0,
                "gameStatus": data.get("gameStatus", "SETUP"),
                "events": [], "playerStats": {}, "stats": {}, "extras": {},
                "lowerThird": None, "celebration": None,
                "announcement": "", "annSeq": 0,
                "sponsors": [], "adSchedule": [],
            })
            for k in ["sport", "leagueName", "matchday", "season",
                      "homeTeam", "awayTeam", "teamAColor", "teamBColor",
                      "homeLogo", "awayLogo", "gameDate", "gameLocation",
                      "homeRecord", "awayRecord", "kickoff"]:
                if k in data:
                    new_state[k] = data[k]
            ts = int(time.time() * 1000)
            ht = re.sub(r'[^a-z0-9]', '', (data.get("homeTeam") or "home").lower())[:10]
            at = re.sub(r'[^a-z0-9]', '', (data.get("awayTeam") or "away").lower())[:10]
            new_state["id"] = f"game_{ts}_{ht}_vs_{at}"
            new_state["createdAt"] = ts
            new_state["finalizedAt"] = 0
            new_state["gameCode"] = secrets.token_hex(3).upper()
            new_state["requireGameCode"] = bool(data.get("requireGameCode", True))
            save_state(new_state)
            sse_broadcast_state()
            self._send_json({"ok": True, "id": new_state["id"], "gameCode": new_state["gameCode"]})
        except Exception as e:
            self._error(str(e), 500)

    def _handle_finalize_game(self):
        """Snapshot the current live state into the games archive and mark FT."""
        try:
            s = load_state()
            if s.get("gameStatus") == "FT":
                return self._send_json({"ok": True, "id": s.get("id", ""), "alreadyFinalized": True})
            game_id = s.get("id") or f"game_{int(time.time() * 1000)}"
            s["id"] = game_id
            s["finalizedAt"] = int(time.time() * 1000)
            s["gameStatus"] = "FT"
            dest = GAMES_DIR / f"{game_id}.json"
            with open(dest, "w") as f:
                json.dump(s, f, indent=2)
            save_state(s)
            sse_broadcast_state()
            self._send_json({"ok": True, "id": game_id})
        except Exception as e:
            self._error(str(e), 500)

    def _handle_fixtures_post(self):
        """Create or update a fixture."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            fixtures = load_fixtures()
            fix_id = data.get("id")
            if fix_id:
                for i, f in enumerate(fixtures):
                    if f.get("id") == fix_id:
                        fixtures[i] = {**f, **data}
                        break
                else:
                    fixtures.append(data)
            else:
                ts = int(time.time() * 1000)
                ht = re.sub(r'[^a-z0-9]', '', (data.get("homeTeam") or "home").lower())[:10]
                at = re.sub(r'[^a-z0-9]', '', (data.get("awayTeam") or "away").lower())[:10]
                data["id"] = f"fix_{ts}_{ht}_vs_{at}"
                data["createdAt"] = ts
                fixtures.append(data)
            fixtures.sort(key=lambda x: (x.get("date", ""), x.get("kickoff", "")))
            save_fixtures(fixtures)
            self._send_json({"ok": True, "fixture": fixtures[-1] if not fix_id else data})
        except Exception as e:
            self._error(str(e), 500)

    def _handle_fixture_load(self, fix_id):
        """Copy a fixture into the live state.json so the dashboard can finish setup."""
        try:
            fixtures = load_fixtures()
            fix = next((f for f in fixtures if f.get("id") == fix_id), None)
            if not fix:
                return self._error("Fixture not found", 404)
            new_state = dict(DEFAULT_STATE)
            new_state.update({
                "homeScore": 0, "awayScore": 0,
                "period": 0, "clock": "00:00", "clockRunning": False, "clockAnchorWall": 0,
                "gameStatus": "SETUP",
                "events": [], "playerStats": {}, "stats": {}, "extras": {},
                "lowerThird": None, "celebration": None,
            })
            for src, dst in [("sport","sport"), ("leagueName","leagueName"),
                              ("matchday","matchday"), ("season","season"),
                              ("homeTeam","homeTeam"), ("awayTeam","awayTeam"),
                              ("teamAColor","teamAColor"), ("teamBColor","teamBColor"),
                              ("homeLogo","homeLogo"), ("awayLogo","awayLogo"),
                              ("date","gameDate"), ("venue","gameLocation"),
                              ("homeRecord","homeRecord"), ("awayRecord","awayRecord"),
                              ("kickoff","kickoff")]:
                if fix.get(src) is not None:
                    new_state[dst] = fix[src]
            ts = int(time.time() * 1000)
            new_state["id"] = f"game_{ts}"
            new_state["createdAt"] = ts
            new_state["fixtureId"] = fix_id
            save_state(new_state)
            sse_broadcast_state()
            self._send_json({"ok": True})
        except Exception as e:
            self._error(str(e), 500)

    def _handle_delete_game(self, game_id):
        try:
            if not re.match(r'^[\w\-]+$', game_id):
                return self._error("Invalid game id")
            gf = GAMES_DIR / f"{game_id}.json"
            if not gf.exists():
                return self._error("Not found", 404)
            gf.unlink()
            self._send_json({"ok": True})
        except Exception as e:
            self._error(str(e), 500)

    def _handle_players_post(self):
        """Replace the full player roster (JSON body)."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                return self._error("Expected {home:[...], away:[...]}")
            roster = {
                "home": [p for p in data.get("home", []) if p.get("name")],
                "away": [p for p in data.get("away", []) if p.get("name")],
            }
            save_players(roster)
            self._send_json({"ok": True, "counts": {"home": len(roster["home"]), "away": len(roster["away"])}})
        except Exception as e:
            self._error(str(e), 500)

    def _handle_players_upload(self):
        """Upload CSV text, parse it, save and return the roster."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            roster = parse_players_csv(raw)
            save_players(roster)
            self._send_json({
                "ok": True,
                "players": roster,
                "counts": {"home": len(roster["home"]), "away": len(roster["away"])},
            })
        except Exception as e:
            self._error(str(e), 500)

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8765))

    class ThreadedServer(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

        def handle_error(self, request, client_address):
            """Suppress noisy but harmless Windows WinError 10053 / connection-abort tracebacks."""
            import traceback
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
                return  # browser closed the connection — totally normal
            # For any other real error, print the full traceback as usual
            traceback.print_exc()

    httpd = ThreadedServer(("0.0.0.0", PORT), Handler)
    host_note = f"http://localhost:{PORT}"
    print("=" * 64)
    print("  ** SCOREBOARD SERVER STARTED **")
    print("=" * 64)
    print(f"  Login page   ->  {host_note}/login")
    print(f"  Display      ->  {host_note}/display   (public)")
    print(f"  Dashboard    ->  {host_note}/dashboard")
    print(f"  Scorer panel ->  {host_note}/scorer")
    print(f"  XML feed     ->  {host_note}/xml")
    print(f"  Data dir     ->  {BASE}")
    print("=" * 64)
    print("  DEFAULT USERS (change in users.json!):")
    print("    admin / admin        (full access)")
    print("    operator / operator  (match operations)")
    print("    scorer / scorer      (scoring only)")
    print("=" * 64)
    print("  Press Ctrl+C to stop.")
    print()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] stopped.")
        sys.exit(0)
