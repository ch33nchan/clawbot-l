"""
FAL FLUX.2 Klein 9B LoRA - Face Swap Script

Uses FAL's flux-2/klein/9b/base/edit/lora model with BFS-Best-Face-Swap LoRA.
Takes base image + character image and generates face-swapped result.

API: https://fal.ai/models/fal-ai/flux-2/klein/9b/base/edit/lora/api
LoRA: https://huggingface.co/Alissonerdx/BFS-Best-Face-Swap

Usage:
    python scripts/fal_klein_lora_faceswap.py --input datasets/klein_lora_faceswap_input.json --output outputs/klein_lora_faceswap_results.json --limit 2

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


def run_klein_lora_faceswap(
    base_image_url: str,
    char_image_url: str,
    lora_url: str,
    fal_key: str,
    prompt: str = "Apply the face from the second image onto the person in the first image. Keep the pose, clothing, and background from the first image. Make it look natural and realistic.",
    lora_scale: float = 1.0,
    timeout_seconds: int = 300,
) -> dict:
    """
    Run face swap using FAL flux-2/klein/9b/base/edit/lora with BFS LoRA.
    
    Args:
        base_image_url: URL of the base/original image
        char_image_url: URL of the character/face image
        lora_url: URL of the LoRA weights
        fal_key: FAL API key
        prompt: Edit prompt
        lora_scale: LoRA weight scale
        timeout_seconds: Max time to wait for result
        
    Returns:
        dict with result URL and metadata
    """
    endpoint = "https://fal.run/fal-ai/flux-2/klein/9b/base/edit/lora"
    
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "prompt": prompt,
        "image_urls": [base_image_url, char_image_url],
        "num_images": 1,
        "output_format": "png",
        "guidance_scale": 5,
        "num_inference_steps": 28,
        "loras": [
            {
                "path": lora_url,
                "scale": lora_scale
            }
        ]
    }
    
    response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    
    return response.json()


def download_image(url: str) -> bytes:
    """Download image from URL."""
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def process_entries(
    input_json_path: str,
    output_json_path: str,
    upload_to_cdn: bool = True,
    limit: int = None,
) -> dict:
    """
    Process entries from input JSON.
    
    Args:
        input_json_path: Path to input JSON with entries
        output_json_path: Path to save results JSON
        upload_to_cdn: Whether to re-upload results to Azure CDN
        limit: Max number of entries to process (None = all)
        
    Returns:
        Results dict
    """
    load_env()
    if upload_to_cdn:
        load_azure_env()
    
    fal_key = get_fal_key()
    
    with open(input_json_path) as f:
        input_data = json.load(f)
    
    lora_url = input_data.get("lora_url")
    
    results = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": input_json_path,
        "model": "fal-ai/flux-2/klein/9b/base/edit/lora",
        "lora_url": lora_url,
        "results": [],
    }
    
    entries = input_data["entries"]
    if limit:
        entries = entries[:limit]
    
    for entry in entries:
        print(f"Processing {entry['id']}...")
        
        try:
            fal_result = run_klein_lora_faceswap(
                base_image_url=entry["base_image_url"],
                char_image_url=entry["char_image_url"],
                lora_url=lora_url,
                fal_key=fal_key,
            )
            
            # Extract result image URL
            images = fal_result.get("images", [])
            result_image_url = images[0].get("url") if images else None
            
            cdn_url = None
            if upload_to_cdn and result_image_url:
                image_bytes = download_image(result_image_url)
                blob_name = f"rawclaw/klein-lora-faceswap/results/{entry['id']}.png"
                cdn_url = upload_bytes_to_azure(
                    data=image_bytes,
                    blob_name=blob_name,
                    content_type="image/png",
                )
                print(f"  ✅ Uploaded to CDN: {cdn_url}")
            
            results["results"].append({
                "id": entry["id"],
                "row_number": entry["row_number"],
                "base_image_url": entry["base_image_url"],
                "char_image_url": entry["char_image_url"],
                "fal_result_url": result_image_url,
                "cdn_url": cdn_url,
                "status": "success",
            })
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results["results"].append({
                "id": entry["id"],
                "row_number": entry["row_number"],
                "base_image_url": entry["base_image_url"],
                "char_image_url": entry["char_image_url"],
                "status": "error",
                "error": str(e),
            })
    
    # Save results
    output_path = Path(output_json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\n✅ Results saved to {output_json_path}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="FAL Klein LoRA Face Swap")
    parser.add_argument("--input", "-i", required=True, help="Input JSON with entries")
    parser.add_argument("--output", "-o", required=True, help="Output JSON path for results")
    parser.add_argument("--no-cdn", action="store_true", help="Skip re-uploading to CDN")
    parser.add_argument("--limit", "-n", type=int, help="Limit number of entries to process")
    
    args = parser.parse_args()
    
    process_entries(
        input_json_path=args.input,
        output_json_path=args.output,
        upload_to_cdn=not args.no_cdn,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
