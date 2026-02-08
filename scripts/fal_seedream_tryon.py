"""
FAL Bytedance SeedDream v4 Edit - Virtual Try-On Script

Uses FAL's seedream/v4/edit model for virtual try-on.
Takes human image + garment image and generates try-on result.

API: https://fal.ai/models/fal-ai/bytedance/seedream/v4/edit/api

Usage:
    python scripts/fal_seedream_tryon.py --human <url> --garment <url> --output <path>

Environment:
    FAL_KEY: Your FAL API key
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# Add parent to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.upload_file_to_azure import load_env as load_azure_env, upload_bytes_to_azure


def load_env(env_path: str = ".env") -> None:
    """Load environment variables."""
    load_dotenv(dotenv_path=Path(env_path), override=False)


def get_fal_key() -> str:
    """Get FAL API key from environment."""
    key = os.getenv("FAL_KEY")
    if not key:
        raise ValueError("Missing FAL_KEY environment variable")
    return key


def run_seedream_tryon(
    human_url: str,
    garment_url: str,
    fal_key: str,
    prompt: str = "Dress the person in the first image with the clothing/garment shown in the second image. Keep the person's face, pose, and background exactly the same. Make it look natural and realistic.",
    timeout_seconds: int = 300,
) -> dict:
    """
    Run virtual try-on using FAL SeedDream v4 Edit.
    
    Args:
        human_url: URL of the human/model image
        garment_url: URL of the garment image
        fal_key: FAL API key
        prompt: Edit prompt for try-on
        timeout_seconds: Max time to wait for result
        
    Returns:
        dict with result URL and metadata
    """
    endpoint = "https://fal.run/fal-ai/bytedance/seedream/v4/edit"
    
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "prompt": prompt,
        "image_urls": [human_url, garment_url],
        "num_images": 1,
        "enable_safety_checker": True,
    }
    
    response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    
    return response.json()


def download_image(url: str) -> bytes:
    """Download image from URL."""
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def main():
    parser = argparse.ArgumentParser(description="FAL SeedDream Virtual Try-On")
    parser.add_argument("--human", "-h", required=True, help="Human image URL")
    parser.add_argument("--garment", "-g", required=True, help="Garment image URL")
    parser.add_argument("--output", "-o", help="Output JSON path")
    parser.add_argument("--upload-cdn", action="store_true", help="Upload result to CDN")
    parser.add_argument("--blob-name", help="CDN blob name for upload")
    
    args = parser.parse_args()
    
    load_env()
    fal_key = get_fal_key()
    
    print(f"Running SeedDream v4 try-on...")
    print(f"  Human: {args.human}")
    print(f"  Garment: {args.garment}")
    
    result = run_seedream_tryon(
        human_url=args.human,
        garment_url=args.garment,
        fal_key=fal_key,
    )
    
    images = result.get("images", [])
    result_url = images[0].get("url") if images else None
    
    print(f"✅ FAL Result: {result_url}")
    
    cdn_url = None
    if args.upload_cdn and result_url:
        load_azure_env()
        image_bytes = download_image(result_url)
        blob_name = args.blob_name or f"rawclaw/seedream-tryon/{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.png"
        cdn_url = upload_bytes_to_azure(
            data=image_bytes,
            blob_name=blob_name,
            content_type="image/png",
        )
        print(f"✅ CDN URL: {cdn_url}")
    
    output_data = {
        "human_url": args.human,
        "garment_url": args.garment,
        "fal_result_url": result_url,
        "cdn_url": cdn_url,
        "seed": result.get("seed"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(output_data, indent=2))
        print(f"✅ Saved to {args.output}")
    
    print(json.dumps(output_data, indent=2))
    return output_data


if __name__ == "__main__":
    main()
