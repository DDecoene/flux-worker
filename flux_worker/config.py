import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "stabilityai/stable-diffusion-2-1"


@dataclass
class Config:
    hf_token: str | None
    model: str
    output_dir: Path


def load_config(hf_token=None, model=None, output_dir="./output") -> Config:
    """Load configuration for local inference.

    Args:
        hf_token: Optional HuggingFace token (for gated models)
        model: Model ID from huggingface.co (default: stable-diffusion-2-1)
        output_dir: Where to save generated images

    Returns:
        Config object with model and output directory
    """
    token = hf_token or os.environ.get("HF_TOKEN")
    return Config(
        hf_token=token,
        model=model or os.environ.get("HF_MODEL", DEFAULT_MODEL),
        output_dir=Path(output_dir),
    )
