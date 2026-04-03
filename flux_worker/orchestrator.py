import time
import traceback

import requests

from flux_worker.config import load_config
from flux_worker.exceptions import UserError
from flux_worker.result import GenerateResult

HF_API_BASE = "https://api-inference.huggingface.co/models"
GENERATE_TIMEOUT = 120   # seconds per image
MODEL_LOAD_MAX_WAIT = 300  # max seconds to wait for model to load on HF side


def generate(
    prompts,
    output_dir="./output",
    hf_token=None,
    model=None,
) -> GenerateResult:
    if isinstance(prompts, str):
        prompts = [prompts]

    try:
        config = load_config(hf_token=hf_token, model=model, output_dir=output_dir)
        config.output_dir.mkdir(parents=True, exist_ok=True)

        paths = []
        for i, prompt in enumerate(prompts):
            print(f"Generating image {i+1}/{len(prompts)}: {prompt[:60]}...")
            path = _generate_image(config, prompt, i)
            print(f"Saved: {path}")
            paths.append(path)

        return GenerateResult(ok=True, images=paths)

    except UserError as e:
        return GenerateResult(ok=False, error_type="user_error", error_message=str(e))
    except Exception as e:
        tb = traceback.format_exc()
        return GenerateResult(ok=False, error_type="unexpected", error_message=str(e), traceback=tb)


def _generate_image(config, prompt: str, index: int):
    url = f"{HF_API_BASE}/{config.hf_model}"
    headers = {"Authorization": f"Bearer {config.hf_token}"}
    deadline = time.time() + MODEL_LOAD_MAX_WAIT

    while True:
        resp = requests.post(url, headers=headers, json={"inputs": prompt}, timeout=GENERATE_TIMEOUT)

        if resp.status_code == 200:
            path = config.output_dir / f"image_{index}.png"
            path.write_bytes(resp.content)
            return path

        if resp.status_code == 401:
            raise UserError("HuggingFace token is invalid. Check your HF_TOKEN.")

        if resp.status_code == 503:
            if time.time() >= deadline:
                raise RuntimeError(f"Model did not load within {MODEL_LOAD_MAX_WAIT}s.")
            try:
                wait = resp.json().get("estimated_time", 20)
            except Exception:
                wait = 20
            print(f"  Model loading, waiting {wait:.0f}s...")
            time.sleep(min(wait, deadline - time.time()))
            continue

        resp.raise_for_status()
