import base64
import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class CallbackServer:
    def __init__(self, token: str):
        self.token = token
        self.events = queue.Queue()
        self._response_queue = queue.Queue()
        self._server = None
        self._thread = None
        self.port = None

    def start(self) -> int:
        self._server = HTTPServer(("127.0.0.1", 0), self._make_handler())
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None

    def send_response(self, data: dict):
        self._response_queue.put(data)

    def _wait_for_response(self) -> dict:
        return self._response_queue.get()

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}

                if body.get("token") != server.token:
                    self._respond(403, {"error": "invalid token"})
                    return

                if self.path == "/ready":
                    server.events.put({"type": "ready"})
                    resp = server._wait_for_response()
                    self._respond(200, resp)

                elif self.path == "/done":
                    image_bytes = base64.b64decode(body["image_b64"]) if body.get("image_b64") else None
                    server.events.put({"type": "done", "index": body.get("index", 0), "image_bytes": image_bytes})
                    resp = server._wait_for_response()
                    self._respond(200, resp)

                else:
                    self._respond(404, {"error": "not found"})

            def _respond(self, status, data):
                body = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)

        return Handler
