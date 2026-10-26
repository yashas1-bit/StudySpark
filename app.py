from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

APP_NAME = "StudySpark"
HOST = "127.0.0.1"

def app_dir() -> Path:
    # Keep writable user data outside the packaged executable folder.
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    folder = Path(base) / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder

DATA_FILE = app_dir() / "study_data.json"

def web_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "web"
    return Path(__file__).resolve().parent / "web"

DEFAULT_DATA = {
    "tasks": [],
    "notes": "",
    "flashcards": [],
    "sessions": 0,
    "focus_minutes": 0,
    "updated_at": None,
}

def load_data():
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid data")
        for key, value in DEFAULT_DATA.items():
            data.setdefault(key, value)
        return data
    except (OSError, json.JSONDecodeError, ValueError):
        return dict(DEFAULT_DATA)

def save_data(data):
    temp = DATA_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(DATA_FILE)

class Handler(BaseHTTPRequestHandler):
    server_version = "StudySpark/1.0"

    def log_message(self, fmt, *args):
        # Keep the app's console quiet in normal use.
        return

    def _send(self, status, content, content_type="application/json; charset=utf-8"):
        raw = content if isinstance(content, bytes) else content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/data":
            self._send(200, json.dumps(load_data(), ensure_ascii=False))
            return
        if path == "/" or path == "/index.html":
            target = web_dir() / "index.html"
            if target.exists():
                self._send(200, target.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(500, "App interface missing.", "text/plain; charset=utf-8")
            return
        self._send(404, json.dumps({"error": "Not found"}))

    def do_POST(self):
        if urlparse(self.path).path != "/api/data":
            self._send(404, json.dumps({"error": "Not found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 2_000_000:
                self._send(413, json.dumps({"error": "Request too large"}))
                return
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Data must be an object")
            clean = {
                "tasks": data.get("tasks", []) if isinstance(data.get("tasks", []), list) else [],
                "notes": str(data.get("notes", ""))[:100_000],
                "flashcards": data.get("flashcards", []) if isinstance(data.get("flashcards", []), list) else [],
                "sessions": max(0, int(data.get("sessions", 0))),
                "focus_minutes": max(0, int(data.get("focus_minutes", 0))),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            save_data(clean)
            self._send(200, json.dumps({"ok": True, "updated_at": clean["updated_at"]}))
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, json.dumps({"error": "Invalid data"}))

def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]

def main():
    port = free_port()
    server = ThreadingHTTPServer((HOST, port), Handler)
    url = f"http://{HOST}:{port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"{APP_NAME} is running at {url}")
    print("Your study data is saved locally on this PC.")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()

if __name__ == "__main__":
    main()
