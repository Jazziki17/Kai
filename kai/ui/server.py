"""
Kai Dashboard Server
=====================
A lightweight HTTP server that serves the cyberpunk UI.
"""

import http.server
import json
import os
import threading
import webbrowser
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"
PORT = 3000


class KaiHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler that serves from the static directory."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/status":
            self._send_json({
                "status": "online",
                "modules": {
                    "voice": {"status": "active", "amplitude": 0},
                    "speech": {"status": "active", "last_text": ""},
                    "vision": {"status": "active", "motion": False},
                    "io": {"status": "active", "files": 0},
                },
                "uptime": 0,
            })
        elif self.path == "/api/thoughts":
            self._send_json({
                "thoughts": [
                    {"id": 1, "text": "Initialize voice pipeline", "status": "done", "type": "system"},
                    {"id": 2, "text": "Listening for wake word...", "status": "active", "type": "voice"},
                    {"id": 3, "text": "Camera stream ready", "status": "done", "type": "vision"},
                    {"id": 4, "text": "Analyzing audio patterns", "status": "processing", "type": "speech"},
                    {"id": 5, "text": "Motion detector calibrating", "status": "processing", "type": "vision"},
                    {"id": 6, "text": "Loading NLP model", "status": "pending", "type": "speech"},
                    {"id": 7, "text": "File system indexed", "status": "done", "type": "io"},
                    {"id": 8, "text": "Gesture model warming up", "status": "processing", "type": "vision"},
                ]
            })
        else:
            super().do_GET()

    def _send_json(self, data):
        response = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(response))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        pass  # Suppress request logs


def start_server(port: int = PORT):
    print(f"\033[36m")
    print(f"  ╔══════════════════════════════════════╗")
    print(f"  ║        KAI DASHBOARD v0.1.0          ║")
    print(f"  ║   http://localhost:{port}               ║")
    print(f"  ╚══════════════════════════════════════╝")
    print(f"\033[0m")

    server = http.server.HTTPServer(("", port), KaiHandler)
    webbrowser.open(f"http://localhost:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard shut down.")
        server.server_close()


if __name__ == "__main__":
    start_server()
