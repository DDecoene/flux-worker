#!/usr/bin/env python3
"""End-to-end test of local image generation."""
import sys
from pathlib import Path

# Add repo to path
sys.path.insert(0, str(Path(__file__).parent))

from flux_worker import generate

if __name__ == "__main__":
    result = generate(
        prompts=["a red cube on a blue background"],
        output_dir="./e2e_output",
    )

    if result.ok:
        print(f"\n✓ E2E test passed!")
        print(f"Generated {len(result.images)} image(s):")
        for path in result.images:
            print(f"  - {path}")
        sys.exit(0)
    else:
        print(f"\n✗ E2E test failed!")
        print(f"Error type: {result.error_type}")
        print(f"Error: {result.error_message}")
        if result.traceback:
            print(f"Traceback:\n{result.traceback}")
        sys.exit(1)
