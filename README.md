# flux-worker

Generate images via the [HuggingFace Inference API](https://huggingface.co/inference-api). Defaults to [Stable Diffusion XL](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0).

- **Simple interface** — prompt in, image file out
- **No GPU setup** — runs entirely through the HuggingFace cloud API
- **Batch generation** — pass multiple prompts, images saved locally

## Prerequisites

1. A [HuggingFace account](https://huggingface.co/join)
2. A HuggingFace API token — [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

## Installation

### CLI tool — Homebrew (macOS)

```bash
brew tap ddecoene/tap
brew install flux-worker
```

Then set your token:

```bash
export HF_TOKEN=hf_...
# or put it in a .env file in your working directory
```

### Python library or agentic use — pip or pipx

```bash
# pipx: isolated install, also gives you the CLI
pipx install flux-worker

# pip: install into your project environment
pip install flux-worker
```

### Claude Code agent tool

Add to your `CLAUDE.md` or system prompt:

```
You have access to flux-worker for generating images.
Use the bash tool to run: flux-worker generate "<prompt>"
Images are saved to ./output/ by default.
```

Or call directly from Python:

```python
from flux_worker import generate

def generate_image(prompt: str) -> str:
    result = generate(prompt)
    return str(result.images[0])
```

## Usage

### CLI

```bash
# Single prompt
flux-worker generate "a cyclist at golden hour in the Flemish polders"

# Multiple prompts
flux-worker generate "prompt one" "prompt two" "prompt three"

# From JSON file
flux-worker generate --prompts-file prompts.json

# Custom output directory
flux-worker generate "a cyclist at golden hour" --output ./my-images/

# Use a different model
flux-worker generate "a cyclist" --model stabilityai/stable-diffusion-2-1
```

### Python API

```python
from flux_worker import generate

# Single image
result = generate("a cyclist at golden hour in the Flemish polders")
print(result.images[0])  # Path to saved PNG

# Batch
result = generate([
    "a cyclist at golden hour in the Flemish polders",
    "a runner in the rain, cinematic lighting",
    "a swimmer at sunrise, aerial view",
])

# All options
result = generate(
    prompts=["a cyclist at golden hour"],
    output_dir="./images",
    hf_token="hf_...",     # or set HF_TOKEN in .env
    model="stabilityai/stable-diffusion-xl-base-1.0",  # optional
)
# result.ok — True/False
# result.images — list[Path]
```

### prompts.json format

```json
["prompt one", "prompt two", "prompt three"]
```

## Environment Variables

Place in a `.env` file in your working directory, or export in your shell.

| Variable | Description | Required |
|---|---|---|
| `HF_TOKEN` | HuggingFace API token | Yes |
| `HF_MODEL` | Model ID to use | No (default: `stabilityai/stable-diffusion-xl-base-1.0`) |

## License

Apache-2.0
