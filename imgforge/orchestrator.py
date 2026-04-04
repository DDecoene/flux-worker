import traceback
from diffusers import FluxPipeline
import torch

from imgforge.config import load_config
from imgforge.exceptions import UserError, ImgForgeError
from imgforge.result import GenerateResult

_PIPELINE = None


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


def _get_pipeline(model_id: str, hf_token: str | None = None):
    global _PIPELINE
    if _PIPELINE is None:
        try:
            _PIPELINE = FluxPipeline.from_pretrained(
                model_id,
                torch_dtype=torch.bfloat16,  # bfloat16 required on MPS — float16 produces black images
                token=hf_token,
            )
            _PIPELINE.to("mps")
            _PIPELINE.enable_attention_slicing()
        except Exception as e:
            raise ImgForgeError(f"Failed to load model {model_id}: {e}")
    return _PIPELINE


def _generate_image(config, prompt: str, index: int):
    try:
        pipeline = _get_pipeline(config.model, hf_token=config.hf_token)
        image = pipeline(
            prompt,
            num_inference_steps=4,   # FLUX.1-schnell optimal
            guidance_scale=0.0,      # FLUX.1-schnell is guidance-distilled
            width=1280,
            height=720,
        ).images[0]
        path = config.output_dir / f"image_{index}.png"
        image.save(str(path))
        return path
    except ImgForgeError:
        raise
    except Exception as e:
        raise ImgForgeError(f"Image generation failed: {e}")
