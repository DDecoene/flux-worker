import queue as q
import time
import traceback
import uuid
from pathlib import Path

from flux_worker.callback_server import CallbackServer
from flux_worker.config import load_config
from flux_worker.exceptions import UserError, VastAIError
from flux_worker.result import GenerateResult
from flux_worker.tunnel import Tunnel
from flux_worker import vastai

READY_TIMEOUT = 1800    # 30 min
IMAGE_TIMEOUT = 600     # 10 min per image
LOG_POLL_INTERVAL = 30  # seconds


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
    tunnel = Tunnel()
    server = None
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
            print(f"Resuming existing instance {instance_id} (token: {token[:8]}...)")
        else:
            token = str(uuid.uuid4())

        # Start callback server + tunnel
        server = CallbackServer(token)
        port = server.start()
        print("Starting cloudflared tunnel...")
        callback_url = tunnel.start(port)
        print(f"Callback URL: {callback_url}")

        if resumable:
            # GPU has old tunnel URL in its env — update it so the next /ready retry reaches us
            print("Updating instance CALLBACK_URL to new tunnel...")
            try:
                vastai.update_instance_env(
                    config.vastai_api_key,
                    instance_id,
                    {"CALLBACK_URL": callback_url, "CALLBACK_TOKEN": token},
                )
                print("Instance env updated. Waiting for GPU to retry /ready...")
            except Exception as e:
                print(f"Warning: could not update instance env: {e}")
                print("GPU may not be able to reach new tunnel URL.")

        if not resumable:
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
                callback_url=callback_url,
                callback_token=token,
                label=f"flux-worker-token:{token}",
            )
            instance_id = result["new_contract"]
            print(f"Instance {instance_id} created. Waiting for /ready (up to 30 min)...")

        paths = _run_job(config, server, instance_id, prompts)
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
        if server:
            server.stop()
        tunnel.stop()


def _run_job(config, server: CallbackServer, instance_id: int, prompts: list) -> list:
    paths = [None] * len(prompts)

    # Wait for /ready
    event = _wait_for_event(server, READY_TIMEOUT, config.vastai_api_key, instance_id)
    if event["type"] != "ready":
        raise RuntimeError(f"Expected 'ready' event, got: {event['type']}")

    print("GPU is ready. Sending first prompt...")
    server.send_response({"prompt": prompts[0], "index": 0})

    for i in range(len(prompts)):
        print(f"Waiting for image {i+1}/{len(prompts)}...")
        event = _wait_for_event(server, IMAGE_TIMEOUT, config.vastai_api_key, instance_id)

        if event["type"] != "done":
            raise RuntimeError(f"Expected 'done' event, got: {event['type']}")

        local_path = config.output_dir / f"image_{i}.png"
        local_path.write_bytes(event["image_bytes"])
        print(f"Saved: {local_path}")
        paths[i] = local_path

        if i + 1 < len(prompts):
            server.send_response({"prompt": prompts[i + 1], "index": i + 1})
        else:
            server.send_response({"done": True})

    return paths


def _wait_for_event(server: CallbackServer, timeout: int, api_key: str, instance_id: int) -> dict:
    """Wait for next event from GPU, polling logs while waiting."""
    deadline = time.time() + timeout
    seen_log_lines = set()
    last_log_poll = 0

    while time.time() < deadline:
        try:
            return server.events.get(timeout=LOG_POLL_INTERVAL)
        except q.Empty:
            pass

        now = time.time()
        if now - last_log_poll >= LOG_POLL_INTERVAL:
            logs = vastai.get_instance_logs(api_key, instance_id)
            for line in logs.splitlines():
                if line and line not in seen_log_lines:
                    print(f"  [gpu] {line}")
                    seen_log_lines.add(line)
            last_log_poll = now

    raise TimeoutError(f"Timed out after {timeout}s waiting for GPU callback")
