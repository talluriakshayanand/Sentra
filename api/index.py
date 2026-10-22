
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
        expiry = getattr(self, "_session_expiry", {}).get(token)
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
            self.send_json(503, {
                "error": "Session storage needs persistent configuration"
            })
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
            self.send_json(503, {
                "error": "Session storage needs persistent configuration"
            })
        else:
            self.send_json(404, {"error": "Not found"})

    def login(self, data):
        if not ACCESS_CODE:
            self.send_json(503, {"error": "Login is not configured"})
            return

        supplied = data.get("code", data.get("access_code", ""))
        if not isinstance(supplied, str) or not hmac.compare_digest(
            supplied, ACCESS_CODE
        ):
            self.send_json(401, {"error": "Invalid access code"})
            return

        self.send_json(200, {
            "message": "Access code verified",
            "mode": "prototype"
        })
