import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
from flux_worker.exceptions import UserError

load_dotenv()

HF_DEFAULT_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"


@dataclass
class Config:
    hf_token: str
    hf_model: str
    output_dir: Path


def load_config(hf_token=None, model=None, output_dir="./output") -> Config:
    token = hf_token or os.environ.get("HF_TOKEN")
    if not token:
        raise UserError(
            "Missing HF_TOKEN.\n"
            "  Set it in .env or pass --hf-token."
        )
    return Config(
        hf_token=token,
        hf_model=model or os.environ.get("HF_MODEL", HF_DEFAULT_MODEL),
        output_dir=Path(output_dir),
    )
