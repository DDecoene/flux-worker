import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    vastai_api_key: str
    ssh_key_path: Path
    max_gpu_price: float
    min_vram_gb: int
    min_cuda_version: float
    disk_gb: int
    output_dir: Path

def load_config(
    vastai_api_key=None,
    ssh_key_path=None,
    max_gpu_price=None,
    min_vram_gb=None,
    min_cuda_version=None,
    disk_gb=None,
    output_dir="./output",
) -> Config:
    api_key = vastai_api_key or os.environ.get("VASTAI_API_KEY")
    if not api_key:
        raise ValueError("VASTAI_API_KEY is required. Set it in .env or pass vastai_api_key=.")

    # SSH key: try explicit, then env, then id_ed25519, then id_rsa
    if ssh_key_path:
        key = Path(ssh_key_path).expanduser()
    elif os.environ.get("SSH_KEY_PATH"):
        key = Path(os.environ["SSH_KEY_PATH"]).expanduser()
    else:
        key = Path("~/.ssh/id_ed25519").expanduser()
        if not key.exists():
            key = Path("~/.ssh/id_rsa").expanduser()

    if not key.exists():
        raise FileNotFoundError(
            f"SSH key not found at {key}. "
            "Create one or set SSH_KEY_PATH. "
            "The key must be registered in your Vast.ai account settings."
        )

    return Config(
        vastai_api_key=api_key,
        ssh_key_path=key,
        max_gpu_price=float(max_gpu_price or os.environ.get("MAX_GPU_PRICE", 0.50)),
        min_vram_gb=int(min_vram_gb or os.environ.get("MIN_VRAM_GB", 16)),
        min_cuda_version=float(min_cuda_version or os.environ.get("MIN_CUDA_VERSION", 12.0)),
        disk_gb=int(disk_gb or os.environ.get("DISK_GB", 50)),
        output_dir=Path(output_dir),
    )
