
import hmac
import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import psycopg

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "5000"))
ACCESS_CODE = os.environ.get("SENTRA_ACCESS_CODE", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

MAX_BODY = 16_384
TOKEN_LIFETIME = 12 * 60 * 60
SESSION_LOCK = threading.Lock()

sessions = {}
login_attempts = {}
LOGIN_LOCK = threading.Lock()
BASE_DIR = Path(__file__).resolve().parent


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

    with SESSION_LOCK:
        expired = [
            token for token, expiry in sessions.items()
            if expiry <= now
        ]

        for token in expired:
            sessions.pop(token, None)


class Handler(BaseHTTPRequestHandler):
    server_version = "SENTRA"

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type", "application/json; charset=utf-8"
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None

        if size < 1 or size > MAX_BODY:
            return None

        try:
            data = json.loads(self.rfile.read(size))
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def authenticated(self):
        auth = self.headers.get("Authorization", "")

        if not auth.startswith("Bearer "):
            return False

        token = auth[7:]
        prune_sessions()

        with SESSION_LOCK:
            expiry = sessions.get(token)

            return (
                expiry is not None
                and expiry > time.time()
            )

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/health":
            self.send_json(200, {
                "service": "SENTRA",
                "status": "online",
                "mode": "prototype"
            })
            return

        if path in ("/", "/mobile.html"):
            self.serve_mobile()
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

                incidents = [{
                    "id": row[0],
                    "received_at": row[1].isoformat(),
                    "lat": row[2],
                    "lon": row[3],
                    "source": row[4],
                    "status": row[5],
                    "mode": row[6]
                } for row in rows]

                self.send_json(200, {"incidents": incidents})

            except Exception:
                self.send_json(
                    503, {"error": "Storage unavailable"}
                )

            return

        self.send_json(404, {"error": "Not found"})

    def serve_mobile(self):
        try:
            page = (BASE_DIR / "mobile.html").read_bytes()

            self.send_response(200)
            self.send_header(
                "Content-Type", "text/html; charset=utf-8"
            )
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(page)

        except OSError:
            self.send_json(404, {"error": "Mobile page not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        data = self.read_json()

        if data is None:
            self.send_json(400, {"error": "Invalid request body"})
            return

        if path == "/api/login":
            self.login(data)
            return

        if path == "/api/sos":
            self.receive_sos(data)
            return

        self.send_json(404, {"error": "Not found"})

    def login(self, data):
        if not ACCESS_CODE:
            self.send_json(
                503, {"error": "Login is not configured"}
            )
            return

        client = self.client_address[0]
        now = time.time()

        with LOGIN_LOCK:
            attempts = [
                stamp
                for stamp in login_attempts.get(client, [])
                if now - stamp < 300
            ]

            if len(attempts) >= 5:
                login_attempts[client] = attempts
                self.send_json(
                    429, {"error": "Try again later"}
                )
                return

            supplied = data.get(
                "code", data.get("access_code", "")
            )

            valid = (
                isinstance(supplied, str)
                and hmac.compare_digest(supplied, ACCESS_CODE)
            )

            if not valid:
                attempts.append(now)
                login_attempts[client] = attempts
                self.send_json(
                    401, {"error": "Invalid access code"}
                )
                return

            login_attempts.pop(client, None)

        token = secrets.token_urlsafe(32)
        prune_sessions()

        with SESSION_LOCK:
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
            isinstance(lat, bool)
            or not isinstance(lat, (int, float))
            or isinstance(lon, bool)
            or not isinstance(lon, (int, float))
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
        ):
            self.send_json(
                400, {"error": "Valid GPS coordinates required"}
            )
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
                    incident["id"],
                    incident["received_at"],
                    incident["lat"],
                    incident["lon"],
                    incident["source"],
                    incident["status"],
                    incident["mode"]
                ))

            incident["received_at"] = received_at.isoformat()

            self.send_json(202, {
                "message": "Simulated SOS saved",
                "incident": incident
            })

        except Exception:
            self.send_json(
                503, {"error": "Could not save incident"}
            )

    def log_message(self, fmt, *args):
        print("SENTRA request processed")


def main():
    if not ACCESS_CODE:
        raise SystemExit(
            "Missing SENTRA_ACCESS_CODE environment variable."
        )

    if not DATABASE_URL:
        raise SystemExit(
            "Missing DATABASE_URL environment variable."
        )

    initialise_database()

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SENTRA prototype API listening on port {PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping SENTRA server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
