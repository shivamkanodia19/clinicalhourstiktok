"""
generators/nano_banana.py — Nano Banana API image generation.

Exports a single function:
    generate_asset(prompt, output_path)

Saves raw output to assets/generated/staging/[slug].png and prints a
staging notice. Does NOT move to assets/generated/ automatically.
The orchestrator is responsible for checking whether the asset has been
manually approved and moved to assets/generated/ before compositing.
"""

from __future__ import annotations
import os
import re
import requests
from pathlib import Path


_STAGING_DIR = Path(__file__).parent.parent / "assets" / "generated" / "staging"
_API_BASE    = "https://api.nanobanana.io/v1/generate"   # placeholder endpoint


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:40]


def generate_asset(prompt: str, output_path: str | Path | None = None) -> Path:
    """
    Call the Nano Banana API to generate an image for `prompt`.

    Args:
        prompt:      Text description of the image to generate.
        output_path: Optional explicit output path. If omitted, a slug-based
                     path inside assets/generated/staging/ is used.

    Returns:
        Path to the saved staging file.

    Raises:
        EnvironmentError  — NANO_BANANA_KEY not set in environment.
        RuntimeError      — API call failed or returned no image bytes.

    Side effects:
        Prints: "STAGING: [filename] — approve before compositing"
    """
    api_key = os.environ.get("NANO_BANANA_KEY")
    if not api_key:
        raise EnvironmentError(
            "NANO_BANANA_KEY is not set. Add it to your .env file."
        )

    _STAGING_DIR.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        slug        = _slugify(prompt)
        output_path = _STAGING_DIR / f"{slug}.png"
    output_path = Path(output_path)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "prompt": prompt,
        "width":  1080,
        "height": 1920,
        "format": "png",
    }

    response = requests.post(_API_BASE, json=payload, headers=headers, timeout=60)
    if not response.ok:
        raise RuntimeError(
            f"Nano Banana API error {response.status_code}: {response.text[:200]}"
        )

    image_bytes = response.content
    if not image_bytes:
        raise RuntimeError("Nano Banana API returned an empty response body.")

    output_path.write_bytes(image_bytes)

    print(f"STAGING: {output_path.name} — approve before compositing")
    return output_path
