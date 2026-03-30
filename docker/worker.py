import base64
import os
import time
from pathlib import Path
import requests

CALLBACK_URL = os.environ["CALLBACK_URL"]
CALLBACK_TOKEN = os.environ["CALLBACK_TOKEN"]
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

READY_RETRIES = 5
READY_INTERVAL = 300  # 5 minutes


def callback(path: str, data: dict) -> dict:
    resp = requests.post(f"{CALLBACK_URL}{path}", json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def call_ready() -> dict:
    """Call /ready with retries. Returns response dict."""
    for attempt in range(1, READY_RETRIES + 1):
        try:
            print(f"Calling /ready (attempt {attempt}/{READY_RETRIES})...")
            return callback("/ready", {"token": CALLBACK_TOKEN})
        except Exception as e:
            print(f"  /ready failed: {e}")
            if attempt < READY_RETRIES:
                print(f"  Retrying in {READY_INTERVAL}s...")
                time.sleep(READY_INTERVAL)
    raise RuntimeError(f"/ready failed after {READY_RETRIES} attempts")


# Signal readiness and get first prompt
response = call_ready()

# Load model once
print("Loading model...")
import torch
from diffusers import FluxPipeline

pipe = FluxPipeline.from_pretrained("/model", torch_dtype=torch.bfloat16)
pipe = pipe.to("cuda")
print("Model loaded.")

while True:
    prompt = response.get("prompt")
    index = response.get("index", 0)

    if not prompt:
        print("No prompt in response, exiting.")
        break

    print(f"Generating image {index}: {prompt[:60]}")
    try:
        image = pipe(prompt, num_inference_steps=4, guidance_scale=0.0).images[0]
        img_path = OUTPUT_DIR / f"image_{index}.png"
        image.save(img_path)

        with open(img_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        print(f"Sending /done for index {index}...")
        response = callback("/done", {
            "token": CALLBACK_TOKEN,
            "index": index,
            "image_b64": image_b64,
        })

        if response.get("done"):
            print("All done. Exiting.")
            break

    except Exception as e:
        print(f"Error generating image {index}: {e}")
        break
