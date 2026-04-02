import base64
import time
import traceback
import uuid

import requests

from flux_worker.config import load_config
from flux_worker.exceptions import UserError, VastAIError
from flux_worker.result import GenerateResult
from flux_worker import vastai

HEALTH_TIMEOUT = 1800    # 30 min for instance startup + model load
GENERATE_TIMEOUT = 600   # 10 min per image
HEALTH_POLL_INTERVAL = 10
LOG_POLL_INTERVAL = 30


def generate(
    prompts,
    output_dir="./output",
    vastai_api_key=None,
    max_gpu_price=None,
    min_vram_gb=None,
    min_cuda_version=None,
    disk_gb=None,
) -> GenerateResult:
    if isinstance(prompts, str):
        prompts = [prompts]

    config = None
    instance_id = None

    try:
        config = load_config(
            vastai_api_key=vastai_api_key,
            max_gpu_price=max_gpu_price,
            min_vram_gb=min_vram_gb,
            min_cuda_version=min_cuda_version,
            disk_gb=disk_gb,
            output_dir=output_dir,
        )
        config.output_dir.mkdir(parents=True, exist_ok=True)

        # Check for resumable instance
        resumable = vastai.find_resumable_instance(config.vastai_api_key)
        if resumable:
            instance_id = resumable["id"]
            token = (resumable.get("label") or "").replace("flux-worker-token:", "")
            print(f"Resuming existing instance {instance_id}")
        else:
            token = str(uuid.uuid4())
            print(f"Finding GPU (max ${config.max_gpu_price}/hr, {config.min_vram_gb}GB VRAM)...")
            offer = vastai.find_offer(
                config.vastai_api_key,
                config.max_gpu_price,
                config.min_vram_gb,
                config.min_cuda_version,
            )
            print(f"Found: {offer['gpu_name']} @ ${offer['dph_total']:.3f}/hr (id={offer['id']})")
            print("Renting instance...")
            result = vastai.create_instance(
                config.vastai_api_key,
                offer["id"],
                disk_gb=config.disk_gb,
                worker_token=token,
                label=f"flux-worker-token:{token}",
            )
            instance_id = result["new_contract"]
            print(f"Instance {instance_id} created.")

        # Wait for worker to be ready
        print("Waiting for worker to be ready...")
        worker_url = _wait_for_worker(config.vastai_api_key, instance_id, token)
        print(f"Worker ready at {worker_url}")

        # Generate images
        paths = _generate_images(config, worker_url, token, prompts)
        return GenerateResult(ok=True, images=paths)

    except UserError as e:
        return GenerateResult(ok=False, error_type="user_error", error_message=str(e))
    except VastAIError as e:
        return GenerateResult(ok=False, error_type="vastai_error", error_message=str(e))
    except Exception as e:
        tb = traceback.format_exc()
        return GenerateResult(ok=False, error_type="unexpected", error_message=str(e), traceback=tb, config=config)
    finally:
        if instance_id and config:
            print("Destroying instance...")
            try:
                vastai.destroy_instance(config.vastai_api_key, instance_id)
                print("Instance destroyed.")
            except Exception as e:
                print(f"Warning: failed to destroy instance: {e}")


def _wait_for_worker(api_key: str, instance_id: int, token: str) -> str:
    """Wait for the worker HTTP server to respond to /health. Returns base URL."""
    deadline = time.time() + HEALTH_TIMEOUT
    worker_url = None
    seen_log_lines = set()
    last_log_poll = 0
    last_status = None

    while time.time() < deadline:
        inst = vastai.get_instance(api_key, instance_id)
        if not inst:
            time.sleep(HEALTH_POLL_INTERVAL)
            continue

        status = inst.get("actual_status")
        if status != last_status:
            elapsed = int(HEALTH_TIMEOUT - (deadline - time.time()))
            print(f"  Instance status: {status} ({elapsed}s elapsed)")
            last_status = status

        # Try to extract worker URL once instance is running
        if status == "running" and not worker_url:
            worker_url = vastai.get_worker_url(inst)
            if worker_url:
                print(f"  Worker URL: {worker_url}")

        # Poll /health if we have a URL
        if worker_url:
            try:
                resp = requests.get(
                    f"{worker_url}/health",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5,
                )
                if resp.status_code == 200:
                    return worker_url
            except (requests.ConnectionError, requests.Timeout):
                pass

        # Poll logs periodically
        now = time.time()
        if now - last_log_poll >= LOG_POLL_INTERVAL:
            logs = vastai.get_instance_logs(api_key, instance_id)
            for line in logs.splitlines():
                if line and line not in seen_log_lines:
                    print(f"  [gpu] {line}")
                    seen_log_lines.add(line)
            last_log_poll = now

        time.sleep(HEALTH_POLL_INTERVAL)

    raise TimeoutError(f"Worker not ready after {HEALTH_TIMEOUT}s")


def _generate_images(config, worker_url: str, token: str, prompts: list) -> list:
    """Send each prompt to the worker and download the resulting image."""
    paths = []
    headers = {"Authorization": f"Bearer {token}"}

    for i, prompt in enumerate(prompts):
        print(f"Generating image {i+1}/{len(prompts)}: {prompt[:60]}...")
        resp = requests.post(
            f"{worker_url}/generate",
            json={"prompt": prompt, "index": i},
            headers=headers,
            timeout=GENERATE_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        local_path = config.output_dir / f"image_{i}.png"
        local_path.write_bytes(base64.b64decode(data["image_b64"]))
        print(f"Saved: {local_path}")
        paths.append(local_path)

    return paths
