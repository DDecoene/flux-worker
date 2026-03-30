import json
import requests
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
        "inet_down": {"gte": 300},  # min 300 Mbps download — needed to pull 30GB image in time
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


def create_instance(api_key: str, offer_id: int, disk_gb: int,
                    callback_url: str, callback_token: str, label: str = "") -> dict:
    """Rent the offer and start the worker. Returns instance dict."""
    payload = {
        "client_id": "me",
        "image": DOCKER_IMAGE,
        "disk": disk_gb,
        "label": label,
        "env": {
            "CALLBACK_URL": callback_url,
            "CALLBACK_TOKEN": callback_token,
        },
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


def get_instance_logs(api_key: str, instance_id: int) -> str:
    """Fetch instance logs. Returns log text or empty string."""
    resp = requests.get(
        f"{VASTAI_API}/instances/{instance_id}/logs",
        headers=_headers(api_key),
    )
    try:
        _raise_for_status(resp)
        return resp.json().get("logs") or ""
    except Exception:
        return ""


def find_resumable_instance(api_key: str) -> dict | None:
    """Find a running/loading flux-worker instance with a token label. Returns instance or None."""
    resp = requests.get(f"{VASTAI_API}/instances/", headers=_headers(api_key))
    _raise_for_status(resp)
    for inst in resp.json().get("instances", []):
        label = inst.get("label") or ""
        if (
            label.startswith("flux-worker-token:")
            and inst.get("actual_status") in ("running", "loading")
        ):
            return inst
    return None


def update_instance_env(api_key: str, instance_id: int, env: dict) -> None:
    """Update env vars on a running instance (used to patch CALLBACK_URL on resume)."""
    resp = requests.put(
        f"{VASTAI_API}/instances/{instance_id}/",
        headers=_headers(api_key),
        json={"env": env},
    )
    _raise_for_status(resp)


def destroy_instance(api_key: str, instance_id: int) -> None:
    resp = requests.delete(f"{VASTAI_API}/instances/{instance_id}/", headers=_headers(api_key))
    _raise_for_status(resp)
