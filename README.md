# imgforge

Local image generation for Python. Uses [Stable Diffusion v1.5](https://huggingface.co/runwayml/stable-diffusion-v1-5) via [diffusers](https://github.com/huggingface/diffusers). Designed for 8GB Apple Silicon machines.

- **Simple API** — `generate(prompts)` returns image paths
- **Local inference** — runs on your GPU, no API calls, no cloud
- **Free** — no tokens required
- **1280×720 output** — landscape format, ready for social media

> **Platform**: macOS Apple Silicon (MPS) only. CUDA/Linux not yet supported.

## Requirements

- macOS M1/M2/M3 or newer, 8GB RAM
- ~2.5GB storage for model weights (downloaded once, cached by HuggingFace)

## Installation

Not yet on PyPI. Install directly from GitHub:

```bash
# uv (recommended)
uv add "imgforge @ git+https://github.com/DDecoene/imgforge.git"

# pip
pip install "imgforge @ git+https://github.com/DDecoene/imgforge.git"
```

Pin to a stable tag:

```bash
uv add "imgforge @ git+https://github.com/DDecoene/imgforge.git@v0.3.1"
```

Local editable install (when repos are siblings on disk):

```bash
uv add --editable ../imgforge
```

## Usage

```python
from imgforge import generate

# Single image
result = generate("a cyclist at golden hour in the Flemish polders")
if result.ok:
    print(result.images[0])  # Path to saved PNG
else:
    print(result.error_message)

# Batch
result = generate([
    "a cyclist at golden hour in the Flemish polders",
    "a runner in the rain, cinematic lighting",
    "a swimmer at sunrise, aerial view",
])

# Custom output directory
result = generate(
    prompts=["a cyclist"],
    output_dir="./my-images",
)

print(result.ok)      # True on success
print(result.images)  # [PosixPath('./my-images/image_0.png')]
```

## Result object

| Field | Type | Description |
|---|---|---|
| `ok` | `bool` | `True` on success |
| `images` | `list[Path]` | Paths to generated PNGs (1280×720) |
| `error_type` | `str \| None` | `"user_error"` or `"unexpected"` |
| `error_message` | `str \| None` | Human-readable error |
| `traceback` | `str \| None` | Full traceback on unexpected errors |

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `HF_MODEL` | `runwayml/stable-diffusion-v1-5` | Model ID from huggingface.co |
| `HF_TOKEN` | — | HuggingFace token (not required for the default model) |

## Using with Claude Code or other AI agents

Add to your project's `CLAUDE.md`:

```markdown
## Image generation

This project uses imgforge for local image generation (Apple Silicon only, 8GB RAM).

Install: `uv add --editable ../imgforge` (local) or
         `uv add "imgforge @ git+https://github.com/DDecoene/imgforge.git"`

```python
from imgforge import generate

result = generate("your prompt here", output_dir="./output")
# result.ok (bool), result.images (list of Path), result.error_message (str)
# Output images are 1280×720 PNG
```

- No API keys needed
- First run downloads ~2.5GB model — subsequent calls are instant (cached)
- Images saved as PNG to output_dir/image_{i}.png
```

## License

Apache-2.0
