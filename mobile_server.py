
#!/usr/bin/env python3
"""SENTRA Android SOS bridge — local prototype only."""

import json
import secrets
import sqlite3
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "sentra.db"
PASSCODE_PATH = BASE_DIR / "sentra_access_code.txt"

HOST = "0.0.0.0"
PORT = 5000
TOKEN_TTL = 12 * 60 * 60
MAX_BODY_BYTES = 12000

TOKENS = {}
LOGIN_FAILURES = {}


def load_or_create_passcode():
    if PASSCODE_PATH.exists():
        code = PASSCODE_PATH.read_text(encoding="utf-8").strip()
        if len(code) >= 12:
            return code

    code = secrets.token_urlsafe(16)
    PASSCODE_PATH.write_text(code + "\n", encoding="utf-8")
    return code


ACCESS_CODE = load_or_create_passcode()


def connect_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY,
            time TEXT,
            location TEXT,
            lat REAL,
            lon REAL,
            priority TEXT,
            status TEXT,
            source TEXT
        )
    """)
    conn.commit()
    return conn


class Handler(BaseHTTPRequestHandler):
    server_version = "SENTRAPrototype/1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.client_address[0], fmt % args))

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None

        if length < 1 or length > MAX_BODY_BYTES:
            return None

        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/mobile.html"):
            file_path = BASE_DIR / "mobile.html"

            if not file_path.exists():
                self.send_error(500, "mobile.html is missing")
                return

            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/health":
            self.send_json(200, {"ok": True, "service": "SENTRA"})
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
            self.create_sos(data)
        else:
            self.send_json(404, {"error": "Not found"})

    def login(self, data):
        address = self.client_address[0]
        now = time.time()
        failures = [
            stamp for stamp in LOGIN_FAILURES.get(address, [])
            if now - stamp < 300
        ]
        LOGIN_FAILURES[address] = failures

        if len(failures) >= 5:
            self.send_json(429, {
                "error": "Too many attempts. Wait five minutes."
            })
            return

        supplied = data.get("passcode", "")
        if not isinstance(supplied, str):
            supplied = ""

        if not secrets.compare_digest(supplied, ACCESS_CODE):
            failures.append(now)
            LOGIN_FAILURES[address] = failures
            self.send_json(401, {"error": "Incorrect access code"})
            return

        token = secrets.token_urlsafe(32)
        TOKENS[token] = now + TOKEN_TTL

        self.send_json(200, {"ok": True, "token": token})

    def create_sos(self, data):
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        expiry = TOKENS.get(token, 0)

        if not token or expiry < time.time():
            TOKENS.pop(token, None)
            self.send_json(401, {
                "error": "Session expired. Connect again."
            })
            return

        try:
            lat = float(data["lat"])
            lon = float(data["lon"])
        except (KeyError, TypeError, ValueError):
            self.send_json(400, {"error": "Valid GPS coordinates required"})
            return

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            self.send_json(400, {"error": "GPS coordinates out of range"})
            return

        label = data.get("location_label", "Android GPS")
        if not isinstance(label, str):
            label = "Android GPS"

        location = f"{label[:150]} ({lat:.6f}, {lon:.6f})"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            with connect_db() as conn:
                cursor = conn.execute("""
                    INSERT INTO incidents
                        (time, location, lat, lon, priority, status, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp,
                    location,
                    lat,
                    lon,
                    "HIGH",
                    "Active",
                    "ANDROID DEVICE"
                ))
                incident_id = cursor.lastrowid

            self.send_json(201, {
                "ok": True,
                "incident_id": incident_id,
                "message": "Test alert saved to SENTRA"
            })
        except sqlite3.Error:
            self.send_json(500, {
                "error": "Could not save the incident to the database"
            })


def main():
    if not (BASE_DIR / "mobile.html").exists():
        print("ERROR: mobile.html is missing from", BASE_DIR)
        return

    try:
        with ThreadingHTTPServer((HOST, PORT), Handler) as server:
            print("SENTRA mobile server is running.")
            print("Open on this laptop: http://127.0.0.1:5000")
            print("Health check: http://127.0.0.1:5000/api/health")
            print("Access code is stored in sentra_access_code.txt")
            print("Press Ctrl+C to stop.")
            server.serve_forever()
    except OSError as exc:
        print("Could not start the server:", exc)


if __name__ == "__main__":
    main()
