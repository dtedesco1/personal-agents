"""
Gemini/OpenRouter Image Tools for MCP

This module provides two MCP tools:
  - image.generate(prompt, width?, height?, seed?) -> { filePath }
  - image.edit(imagePath, prompt, maskPath?, seed?) -> { filePath }

Design goals:
  - Optional dependency: uses requests; no SDK required; lazy network calls
  - Provider-agnostic via env vars: IMAGE_PROVIDER=gemini|openrouter
  - Avoids returning raw bytes; writes PNG to disk and returns a file path
  - Extensive docstrings and clear error messages for easy maintenance

Environment variables:
  - IMAGE_PROVIDER: "gemini" (default) or "openrouter"
  - GEMINI_API_KEY, GEMINI_MODEL (default: gemini-2.5-flash-image-preview)
  - OPENROUTER_API_KEY, OPENROUTER_MODEL (default: google/gemini-2.5-flash-image-preview)
  - IMAGE_OUT_DIR: output directory for generated images (default: ./out/images)

Security & privacy:
  - Never logs image bytes or secrets.
  - Only returns file paths to local images.

"""
from __future__ import annotations

import base64
import os
from pathlib import Path
# Use built-in 'dict' in annotations to remain compatible with older FastMCP/Pydantic introspection
from typing import Optional

from mcp_servers.tooling import tool_meta, ToolSpec

# Config (read once at import for defaults; can still override via env before calls)
PROVIDER = os.getenv("IMAGE_PROVIDER", "gemini").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-image-preview")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash-image-preview")
OUT_DIR = Path(os.getenv("IMAGE_OUT_DIR", "./out/images")).resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _require_requests():
    """Import requests lazily and return it, raising a helpful error if missing."""
    try:
        import requests  # type: ignore
        return requests
    except Exception as e:
        raise RuntimeError(
            "Missing optional dependency 'requests'. Install with:\n"
            "  pip install -r requirements/opt-image.txt\n"
        ) from e

# Simple HTTP POST with retry for transient errors and rate limits
# Retries on 429 and 5xx with exponential backoff; honors Retry-After if provided
# This keeps tools resilient without hiding persistent quota issues.
_def_max_attempts = 5
_def_base_sleep = 1.5

def _post_with_retry(requests, url: str, *, max_attempts: int = _def_max_attempts, base_sleep: float = _def_base_sleep, **kwargs):
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(url, **kwargs)
            # Fast path
            if resp.status_code < 400:
                return resp
            # Handle 429 / 5xx explicitly
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                # Calculate sleep
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        sleep_s = float(retry_after)
                    except Exception:
                        sleep_s = base_sleep * (2 ** (attempt - 1))
                else:
                    sleep_s = base_sleep * (2 ** (attempt - 1))
                # On final attempt, break and surface
                if attempt == max_attempts:
                    resp.raise_for_status()
                else:
                    time.sleep(sleep_s)
                    continue
            # Other client errors: raise immediately
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_exc = e
            if attempt == max_attempts:
                raise
            # Backoff on network exceptions as well
            time.sleep(base_sleep * (2 ** (attempt - 1)))
    # Should not reach here
    if last_exc:
        raise last_exc



# ---------------- Provider shims: Gemini -----------------

def _gemini_generate(prompt: str, width: int, height: int, seed: Optional[int]) -> bytes:
    """Call Gemini REST API to generate an image; return PNG bytes.

    Notes:
      - Uses v1beta generateContent. We look for inlineData with image/* mimeType.
      - Width/height are treated as hints; the model may ignore sizing until fully supported.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY")
    requests = _require_requests()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": ({"seed": seed} if seed is not None else {}),
    }
    resp = requests.post(url, json=payload, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    for cand in data.get("candidates", []) or []:
        for p in (cand.get("content") or {}).get("parts", []) or []:
            inline = p.get("inlineData")
            if inline and str(inline.get("mimeType", "")).startswith("image/"):
                return base64.b64decode(inline.get("data", ""))
    raise RuntimeError("No image part found in Gemini response")


def _gemini_edit(prompt: str, image_path: Path, mask_path: Optional[Path], seed: Optional[int]) -> bytes:
    """Edit an image via Gemini using prompt + input image (and optional mask)."""
    if not GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY")
    requests = _require_requests()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    parts = [
        {"text": prompt},
        {"inlineData": {"mimeType": "image/png", "data": img_b64}},
    ]
    if mask_path:
        mask_b64 = base64.b64encode(mask_path.read_bytes()).decode("utf-8")
        parts.append({"inlineData": {"mimeType": "image/png", "data": mask_b64}})
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": ({"seed": seed} if seed is not None else {}),
    }
    resp = requests.post(url, json=payload, timeout=240)
    resp.raise_for_status()
    data = resp.json()
    for cand in data.get("candidates", []) or []:
        for p in (cand.get("content") or {}).get("parts", []) or []:
            inline = p.get("inlineData")
            if inline and str(inline.get("mimeType", "")).startswith("image/"):
                return base64.b64decode(inline.get("data", ""))
    raise RuntimeError("No image part found in Gemini response")


# ---------------- Provider shims: OpenRouter -----------------

def _openrouter_generate(prompt: str, width: int, height: int, seed: Optional[int]) -> bytes:
    """Call OpenRouter chat completions and extract inline image as PNG bytes."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("Missing OPENROUTER_API_KEY")
    requests = _require_requests()
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://local.tool",
        "X-Title": "mcp-image-tool",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=240)
    resp.raise_for_status()
    data = resp.json()
    # Try typical shapes
    try:
        parts = data["choices"][0]["message"]["content"]
        if isinstance(parts, list):
            for p in parts:
                if isinstance(p, dict) and p.get("type") == "image_url":
                    url_str = p.get("image_url", {}).get("url", "")
                    if url_str.startswith("data:image"):
                        b64 = url_str.split(",", 1)[1]
                        return base64.b64decode(b64)
        b64 = data["choices"][0]["message"].get("image_b64")
        if b64:
            return base64.b64decode(b64)
    except Exception:
        pass
    raise RuntimeError("Could not locate image bytes in OpenRouter response")


def _openrouter_edit(prompt: str, image_path: Path, mask_path: Optional[Path], seed: Optional[int]) -> bytes:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("Missing OPENROUTER_API_KEY")
    requests = _require_requests()
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://local.tool",
        "X-Title": "mcp-image-tool",
    }
    img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    content = [
        {"type": "text", "text": prompt},
        {"type": "input_image", "image_data": img_b64, "mime_type": "image/png"},
    ]
    if mask_path:
        mask_b64 = base64.b64encode(mask_path.read_bytes()).decode("utf-8")
        content.append({"type": "input_mask", "image_data": mask_b64, "mime_type": "image/png"})
    payload = {"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": content}]}
    resp = requests.post(url, json=payload, headers=headers, timeout=240)
    resp.raise_for_status()
    data = resp.json()
    try:
        parts = data["choices"][0]["message"]["content"]
        if isinstance(parts, list):
            for p in parts:
                if isinstance(p, dict) and p.get("type") == "image_url":
                    url_str = p.get("image_url", {}).get("url", "")
                    if url_str.startswith("data:image"):
                        b64 = url_str.split(",", 1)[1]
                        return base64.b64decode(b64)
        b64 = data["choices"][0]["message"].get("image_b64")
        if b64:
            return base64.b64decode(b64)
    except Exception:
        pass
    raise RuntimeError("Could not locate image bytes in OpenRouter response")


# ---------------- Public MCP tool functions -----------------

@tool_meta(
    name="image.generate",
    description="Generate an image from a text prompt using the configured provider. Returns a local file path.",
    annotations={"title": "Image Generate", "idempotentHint": False, "destructiveHint": False},
    tags=["image", "generation", "gemini"],
)
def generate_image(prompt: str, width: int = 1024, height: int = 1024, seed: Optional[int] = None) -> dict:
    """
    Generate an image from text.

    Args:
      prompt: Description of the desired image.
      width: Target width (may be treated as a hint by some providers).
      height: Target height (may be treated as a hint).
      seed: Optional seed for determinism if supported.

    Returns:
      {"filePath": "/abs/path/to/output.png"}
    """
    if PROVIDER == "openrouter":
        png = _openrouter_generate(prompt, width, height, seed)
    else:
        png = _gemini_generate(prompt, width, height, seed)
    out = OUT_DIR / f"{int(os.times().elapsed * 1e6)}.png"
    out.write_bytes(png)
    return {"filePath": str(out)}


@tool_meta(
    name="image.edit",
    description="Edit an existing image with a prompt (optionally with a mask). Returns a local file path.",
    annotations={"title": "Image Edit", "idempotentHint": False, "destructiveHint": False},
    tags=["image", "editing", "gemini"],
)
def edit_image(imagePath: str, prompt: str, maskPath: Optional[str] = None, seed: Optional[int] = None) -> dict:
    """
    Edit an image using a text instruction.

    Args:
      imagePath: Absolute or relative path to the source image (PNG recommended).
      prompt: Edit instruction (what to change).
      maskPath: Optional path to a PNG mask (white = keep, black = edit), if supported by the provider.
      seed: Optional seed for determinism if supported.

    Returns:
      {"filePath": "/abs/path/to/output.png"}
    """
    img_p = Path(imagePath).expanduser().resolve()
    if not img_p.exists():
        raise FileNotFoundError(f"imagePath not found: {img_p}")
    mask_p = Path(maskPath).expanduser().resolve() if maskPath else None
    if mask_p and not mask_p.exists():
        raise FileNotFoundError(f"maskPath not found: {mask_p}")

    if PROVIDER == "openrouter":
        png = _openrouter_edit(prompt, img_p, mask_p, seed)
    else:
        png = _gemini_edit(prompt, img_p, mask_p, seed)

    out = OUT_DIR / f"{int(os.times().elapsed * 1e6)}-edit.png"
    out.write_bytes(png)
    return {"filePath": str(out)}


TOOL_SPECS = [
    ToolSpec(func=generate_image),
    ToolSpec(func=edit_image),
]

