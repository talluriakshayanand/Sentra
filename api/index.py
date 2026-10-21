
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

import psycopg

ACCESS_CODE = os.environ.get("SENTRA_ACCESS_CODE", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
TOKEN_LIFETIME = 12 * 60 * 60
MAX_BODY = 16_384

sessions = {}
login_attempts = {}


def database():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL)


def initialise_database():
    with database() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                received_at TIMESTAMPTZ NOT NULL,
                lat DOUBLE PRECISION NOT NULL,
                lon DOUBLE PRECISION NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                mode TEXT NOT NULL
            )
        """)


def prune_sessions():
    now = time.time()
    for token, expiry in list(sessions.items()):
        if expiry <= now:
            sessions.pop(token, None)


class handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > MAX_BODY:
                return None
            data = json.loads(self.rfile.read(size))
            return data if isinstance(data, dict) else None
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def authenticated(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False

        token = auth[7:]
        prune_sessions()
        expiry = sessions.get(token)
        return expiry is not None and expiry > time.time()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/health":
            self.send_json(200, {
                "service": "SENTRA",
                "status": "online",
                "mode": "prototype"
            })
            return

        if path == "/api/incidents":
            if not self.authenticated():
                self.send_json(401, {"error": "Login required"})
                return

            try:
                with database() as conn:
                    rows = conn.execute("""
                        SELECT id, received_at, lat, lon,
                               source, status, mode
                        FROM incidents
                        ORDER BY received_at DESC
                        LIMIT 100
                    """).fetchall()

                self.send_json(200, {
                    "incidents": [{
                        "id": row[0],
                        "received_at": row[1].isoformat(),
                        "lat": row[2],
                        "lon": row[3],
                        "source": row[4],
                        "status": row[5],
                        "mode": row[6]
                    } for row in rows]
                })
            except Exception:
                self.send_json(503, {"error": "Storage unavailable"})
            return

        self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        data = self.read_json()

        if data is None:
            self.send_json(400, {"error": "Invalid request body"})
            return

        if path == "/api/login":
            self.login(data)
        elif path == "/api/sos":
            self.receive_sos(data)
        else:
            self.send_json(404, {"error": "Not found"})

    def login(self, data):
        if not ACCESS_CODE:
            self.send_json(503, {"error": "Login is not configured"})
            return

        client = self.client_address[0]
        now = time.time()
        attempts = [
            stamp for stamp in login_attempts.get(client, [])
            if now - stamp < 300
        ]

        if len(attempts) >= 5:
            self.send_json(429, {"error": "Try again later"})
            return

        supplied = data.get("code", data.get("access_code", ""))
        if not isinstance(supplied, str) or not hmac.compare_digest(
            supplied, ACCESS_CODE
        ):
            attempts.append(now)
            login_attempts[client] = attempts
            self.send_json(401, {"error": "Invalid access code"})
            return

        login_attempts.pop(client, None)
        token = secrets.token_urlsafe(32)
        prune_sessions()
        sessions[token] = time.time() + TOKEN_LIFETIME

        self.send_json(200, {
            "token": token,
            "expires_in": TOKEN_LIFETIME
        })

    def receive_sos(self, data):
        if not self.authenticated():
            self.send_json(401, {"error": "Login required"})
            return

        lat = data.get("lat")
        lon = data.get("lon")

        if (
            isinstance(lat, bool) or not isinstance(lat, (int, float))
            or isinstance(lon, bool) or not isinstance(lon, (int, float))
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
        ):
            self.send_json(400, {"error": "Valid GPS coordinates required"})
            return

        received_at = datetime.now(timezone.utc)
        incident = {
            "id": secrets.token_hex(8),
            "received_at": received_at,
            "lat": float(lat),
            "lon": float(lon),
            "source": "ANDROID DEVICE",
            "status": "ACTIVE - SIMULATED",
            "mode": "SIMULATED SOS"
        }

        try:
            with database() as conn:
                conn.execute("""
                    INSERT INTO incidents
                    (id, received_at, lat, lon, source, status, mode)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    incident["id"], incident["received_at"],
                    incident["lat"], incident["lon"],
                    incident["source"], incident["status"],
                    incident["mode"]
                ))

            incident["received_at"] = received_at.isoformat()
            self.send_json(202, {
                "message": "Simulated SOS saved",
                "incident": incident
            })
        except Exception:
            self.send_json(503, {"error": "Could not save incident"})
