import json
import time
import requests
import paramiko
from flux_worker.exceptions import VastAIError

VASTAI_API = "https://console.vast.ai/api/v0"
DOCKER_IMAGE = "ghcr.io/ddecoene/flux-worker:latest"


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def _raise_for_status(resp) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        try:
            msg = resp.json().get("error") or resp.json().get("msg") or resp.text
        except Exception:
            msg = resp.text
        raise VastAIError(f"Vast.ai error: {msg}")


def find_offer(api_key: str, max_price: float, min_vram_gb: int, min_cuda: float) -> dict:
    """Return cheapest available offer meeting requirements, or raise."""
    params = {
        "rentable": {"eq": True},
        "gpu_ram": {"gte": min_vram_gb * 1024},  # MB
        "dph_total": {"lte": max_price},
        "cuda_vers": {"gte": min_cuda},
        "gpu_name": {"notin": ["Tesla V100", "Tesla V100-SXM2-16GB", "Tesla V100-PCIE-16GB"]},
        "order": [["dph_total", "asc"]],
        "limit": 10,
    }
    resp = requests.get(
        f"{VASTAI_API}/bundles",
        headers=_headers(api_key),
        params={"q": json.dumps(params)},
    )
    _raise_for_status(resp)
    offers = resp.json().get("offers", [])
    if not offers:
        raise RuntimeError(
            f"No GPU available under ${max_price}/hr with {min_vram_gb}GB VRAM and CUDA {min_cuda}+. "
            "Try increasing --max-gpu-price."
        )
    return offers[0]


def create_instance(api_key: str, offer_id: int, prompts: list, disk_gb: int) -> dict:
    """Rent the offer and start the worker. Returns instance dict."""
    payload = {
        "client_id": "me",
        "image": DOCKER_IMAGE,
        "disk": disk_gb,
        "env": {
            "PROMPTS": json.dumps(prompts),
        },
        "onstart": (
            "docker run --gpus all "
            "-e PROMPTS=\"$PROMPTS\" "
            "-v /output:/output "
            f"{DOCKER_IMAGE}"
        ),
    }
    resp = requests.put(
        f"{VASTAI_API}/asks/{offer_id}/",
        headers=_headers(api_key),
        json=payload,
    )
    _raise_for_status(resp)
    return resp.json()


def get_instance(api_key: str, instance_id: int) -> dict | None:
    """Return instance dict or None if not found."""
    resp = requests.get(f"{VASTAI_API}/instances/", headers=_headers(api_key))
    _raise_for_status(resp)
    instances = resp.json().get("instances", [])
    for inst in instances:
        if inst["id"] == instance_id:
            return inst
    return None


def destroy_instance(api_key: str, instance_id: int) -> None:
    resp = requests.delete(f"{VASTAI_API}/instances/{instance_id}/", headers=_headers(api_key))
    _raise_for_status(resp)


def _ssh_client(host: str, port: int, key_path) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username="root",
        key_filename=str(key_path),
        timeout=10,
    )
    return client


def wait_for_ssh(host: str, port: int, key_path, timeout: int = 300) -> None:
    """Poll until SSH is accepting connections, or raise on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            client = _ssh_client(host, port, key_path)
            client.close()
            time.sleep(30)  # daemon needs time to stabilize after first connect
            return
        except Exception:
            time.sleep(5)
    raise TimeoutError(f"SSH not ready after {timeout}s")


def file_exists_ssh(host: str, port: int, key_path, remote_path: str) -> bool:
    client = _ssh_client(host, port, key_path)
    try:
        _, stdout, _ = client.exec_command(f"test -f {remote_path} && echo yes || echo no")
        return stdout.read().decode().strip() == "yes"
    finally:
        client.close()


def download_file_ssh(host: str, port: int, key_path, remote_path: str, local_path) -> None:
    client = _ssh_client(host, port, key_path)
    try:
        sftp = client.open_sftp()
        sftp.get(remote_path, str(local_path))
        sftp.close()
    finally:
        client.close()


def read_file_ssh(host: str, port: int, key_path, remote_path: str) -> str:
    client = _ssh_client(host, port, key_path)
    try:
        _, stdout, _ = client.exec_command(f"cat {remote_path}")
        return stdout.read().decode().strip()
    finally:
        client.close()
