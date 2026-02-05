"""
FAL IDM-VTON - Virtual Try-On / Garment Transfer Script

Runs garment transfer using FAL's idm-vton model.
Takes human + garment image URLs and generates the transfer result.

Usage:
    python scripts/fal_garment_transfer.py --input outputs/garment_transfer_input.json --output outputs/garment_transfer_results.json

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


def run_garment_transfer(
    human_url: str,
    garment_url: str,
    fal_key: str,
    description: str = "A person wearing the garment",
    timeout_seconds: int = 300,
) -> dict:
    """
    Run garment transfer using FAL idm-vton.
    
    Args:
        human_url: URL of the human/model image
        garment_url: URL of the garment image
        fal_key: FAL API key
        description: Description of the output
        timeout_seconds: Max time to wait for result
        
    Returns:
        dict with result URL and metadata
    """
    # FAL idm-vton endpoint (synchronous)
    endpoint = "https://fal.run/fal-ai/idm-vton"
    
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "human_image_url": human_url,
        "garment_image_url": garment_url,
        "description": description,
    }
    
    response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    
    return response.json()


def download_image(url: str) -> bytes:
    """Download image from URL."""
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def process_combinations(
    input_json_path: str,
    output_json_path: str,
    upload_to_cdn: bool = True,
) -> dict:
    """
    Process all combinations from input JSON.
    
    Args:
        input_json_path: Path to input JSON with combinations
        output_json_path: Path to save results JSON
        upload_to_cdn: Whether to re-upload results to Azure CDN
        
    Returns:
        Results dict
    """
    load_env()
    if upload_to_cdn:
        load_azure_env()
    
    fal_key = get_fal_key()
    
    with open(input_json_path) as f:
        input_data = json.load(f)
    
    results = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": input_json_path,
        "results": [],
    }
    
    for combo in input_data["combinations"]:
        print(f"Processing {combo['id']}...")
        
        try:
            fal_result = run_garment_transfer(
                human_url=combo["human_url"],
                garment_url=combo["garment_url"],
                fal_key=fal_key,
                description="A person wearing the garment",
            )
            
            # Extract result image URL
            result_image_url = fal_result.get("image", {}).get("url")
            
            cdn_url = None
            if upload_to_cdn and result_image_url:
                # Download and re-upload to our CDN
                image_bytes = download_image(result_image_url)
                blob_name = f"rawclaw/garment-transfer/results/{combo['id']}.png"
                cdn_url = upload_bytes_to_azure(
                    data=image_bytes,
                    blob_name=blob_name,
                    content_type="image/png",
                )
                print(f"  ✅ Uploaded to CDN: {cdn_url}")
            
            results["results"].append({
                "id": combo["id"],
                "human_url": combo["human_url"],
                "garment_url": combo["garment_url"],
                "fal_result_url": result_image_url,
                "cdn_url": cdn_url,
                "status": "success",
            })
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results["results"].append({
                "id": combo["id"],
                "human_url": combo["human_url"],
                "garment_url": combo["garment_url"],
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
    parser = argparse.ArgumentParser(description="FAL IDM-VTON Garment Transfer")
    parser.add_argument("--input", "-i", required=True, help="Input JSON with combinations")
    parser.add_argument("--output", "-o", required=True, help="Output JSON path for results")
    parser.add_argument("--no-cdn", action="store_true", help="Skip re-uploading to CDN")
    
    args = parser.parse_args()
    
    process_combinations(
        input_json_path=args.input,
        output_json_path=args.output,
        upload_to_cdn=not args.no_cdn,
    )


if __name__ == "__main__":
    main()
