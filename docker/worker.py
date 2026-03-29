import json
import os
from pathlib import Path

output_dir = Path(os.environ.get("OUTPUT_DIR", "/output"))
output_dir.mkdir(parents=True, exist_ok=True)

prompts = json.loads(os.environ["PROMPTS"])

import torch
from diffusers import FluxPipeline

pipe = FluxPipeline.from_pretrained(
    "/model",
    torch_dtype=torch.bfloat16,
)
pipe = pipe.to("cuda")

for i, prompt in enumerate(prompts):
    print(f"Generating {i+1}/{len(prompts)}: {prompt[:60]}")
    try:
        image = pipe(
            prompt,
            num_inference_steps=4,
            guidance_scale=0.0,
        ).images[0]
        image.save(output_dir / f"image_{i}.png")
        (output_dir / f"done_{i}").write_text("ok")
        print(f"Done {i+1}/{len(prompts)}")
    except Exception as e:
        (output_dir / f"done_{i}").write_text(str(e))
        print(f"Error on prompt {i}: {e}")
