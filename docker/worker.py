import base64
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get("WORKER_PORT", "5000"))

# Load model at startup — server won't accept requests until this completes
print("Loading model...")
import torch
from diffusers import FluxPipeline

pipe = FluxPipeline.from_pretrained("/model", torch_dtype=torch.bfloat16)
pipe = pipe.to("cuda")
print("Model loaded.")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(format % args)

    def _check_token(self):
        token = self.headers.get("Authorization", "").replace("Bearer ", "")
        if WORKER_TOKEN and token != WORKER_TOKEN:
            self._respond(403, {"error": "invalid token"})
            return False
        return True

    def do_GET(self):
        if self.path == "/health":
            if not self._check_token():
                return
            self._respond(200, {"status": "ready"})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/generate":
            if not self._check_token():
                return
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            prompt = body["prompt"]
            index = body.get("index", 0)

            print(f"Generating image {index}: {prompt[:60]}")
            image = pipe(prompt, num_inference_steps=4, guidance_scale=0.0).images[0]
            img_path = OUTPUT_DIR / f"image_{index}.png"
            image.save(img_path)

            with open(img_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()

            print(f"Done generating image {index}")
            self._respond(200, {"image_b64": image_b64, "index": index})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


print(f"Starting worker on port {PORT}...")
server = HTTPServer(("0.0.0.0", PORT), Handler)
server.serve_forever()
