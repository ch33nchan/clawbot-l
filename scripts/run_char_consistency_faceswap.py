"""
Char Consistency Face Swap Workflow

Reads from 'Char Consistency F5 Data' sheet, runs Klein LoRA faceswap,
and writes results back to column D.

Usage:
    python scripts/run_char_consistency_faceswap.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import gspread
import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

# Add parent to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.upload_file_to_azure import load_env as load_azure_env, upload_bytes_to_azure


# Config
SHEET_ID = "1g4vcE4dmxq1SmecRPAwXWvDQMcsZFMWae8lCFdi0vvo"
WORKSHEET_NAME = "Char Consistency F5 Data"
SERVICE_ACCOUNT_PATH = "/home/ubuntu/.openclaw/workspace/.secrets/google-service-account.json"
LORA_URL = "https://huggingface.co/Alissonerdx/BFS-Best-Face-Swap/resolve/main/bfs_head_v1_flux-klein_9b_step3750_rank64.safetensors"


def load_env():
    """Load environment variables."""
    load_dotenv(dotenv_path=Path(".env"), override=False)


def extract_url_from_formula(formula: str) -> str | None:
    """Extract URL from IMAGE() formula."""
    if not formula:
        return None
    match = re.search(r'=IMAGE\("([^"]+)"\)', formula)
    return match.group(1) if match else formula


def get_sheet_data() -> list[dict]:
    """Read data from Google Sheet."""
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    
    sheet = gc.open_by_key(SHEET_ID)
    worksheet = sheet.worksheet(WORKSHEET_NAME)
    
    # Get formulas to extract URLs
    range_data = worksheet.get('A1:D20', value_render_option='FORMULA')
    
    entries = []
    for i, row in enumerate(range_data[1:], start=2):  # Skip header, row numbers start at 2
        if len(row) >= 2 and row[0] and row[1]:
            swapped_url = extract_url_from_formula(row[0])
            reference_url = extract_url_from_formula(row[1])
            
            if swapped_url and reference_url:
                entries.append({
                    "id": f"char_f5_{i-1}",
                    "row_number": i,
                    "base_image_url": swapped_url,  # Swapped image is the base
                    "char_image_url": reference_url,  # Reference angle is the face
                })
        
        if len(entries) >= 12:  # Limit to first 12
            break
    
    return entries


def run_klein_lora_faceswap(
    base_image_url: str,
    char_image_url: str,
    fal_key: str,
) -> dict:
    """Run face swap using FAL flux-2/klein/9b/base/edit/lora."""
    endpoint = "https://fal.run/fal-ai/flux-2/klein/9b/base/edit/lora"
    
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "prompt": "head_swap: start with Picture 1 as the base image, keeping its body and scene intact. Replace the head with the head from Picture 2. Match skin tone and lighting naturally.",
        "image_urls": [base_image_url, char_image_url],  # body first, then face (inverted order for BFS Klein)
        "num_images": 1,
        "output_format": "png",
        "guidance_scale": 5,
        "num_inference_steps": 28,
        "loras": [{"path": LORA_URL, "scale": 1.0}]
    }
    
    response = requests.post(endpoint, headers=headers, json=payload, timeout=300)
    response.raise_for_status()
    return response.json()


def download_image(url: str) -> bytes:
    """Download image from URL."""
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def update_sheet_column_d(row_number: int, cdn_url: str):
    """Update column D with IMAGE formula."""
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    
    sheet = gc.open_by_key(SHEET_ID)
    worksheet = sheet.worksheet(WORKSHEET_NAME)
    
    # Update cell D{row_number} with IMAGE formula
    cell = f"D{row_number}"
    formula = f'=IMAGE("{cdn_url}")'
    worksheet.update_acell(cell, formula)


def main():
    import sys
    print("🦅 RAWClaw - Char Consistency Face Swap Workflow", flush=True)
    print("=" * 50, flush=True)
    
    load_env()
    load_azure_env()
    
    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        raise ValueError("Missing FAL_KEY environment variable")
    
    # Step 1: Read sheet data
    print("\n📊 Reading sheet data...")
    entries = get_sheet_data()
    print(f"Found {len(entries)} entries to process")
    
    # Step 2: Save as dataset2 JSON
    dataset2 = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_sheet": SHEET_ID,
        "source_worksheet": WORKSHEET_NAME,
        "lora_url": LORA_URL,
        "entries": entries,
    }
    
    dataset_path = Path("datasets/char_consistency_f5_dataset2.json")
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_text(json.dumps(dataset2, indent=2))
    print(f"✅ Saved dataset2 to {dataset_path}")
    
    # Step 3: Process each entry
    results = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": "fal-ai/flux-2/klein/9b/base/edit/lora",
        "lora_url": LORA_URL,
        "results": [],
    }
    
    # First, add header to column D if not present
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SHEET_ID)
    worksheet = sheet.worksheet(WORKSHEET_NAME)
    worksheet.update_acell("D1", "Automated Results (FAL)")
    
    for entry in entries:
        print(f"\n🔄 Processing {entry['id']} (row {entry['row_number']})...")
        
        try:
            # Run face swap
            fal_result = run_klein_lora_faceswap(
                base_image_url=entry["base_image_url"],
                char_image_url=entry["char_image_url"],
                fal_key=fal_key,
            )
            
            # Extract result image URL
            images = fal_result.get("images", [])
            result_image_url = images[0].get("url") if images else None
            
            if not result_image_url:
                raise ValueError("No result image returned from FAL")
            
            # Upload to CDN
            image_bytes = download_image(result_image_url)
            blob_name = f"rawclaw/char-consistency-f5/results/{entry['id']}.png"
            cdn_url = upload_bytes_to_azure(
                data=image_bytes,
                blob_name=blob_name,
                content_type="image/png",
            )
            print(f"  ✅ Uploaded to CDN")
            
            # Update sheet column D
            update_sheet_column_d(entry["row_number"], cdn_url)
            print(f"  ✅ Updated sheet row {entry['row_number']}")
            
            results["results"].append({
                "id": entry["id"],
                "row_number": entry["row_number"],
                "cdn_url": cdn_url,
                "status": "success",
            })
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results["results"].append({
                "id": entry["id"],
                "row_number": entry["row_number"],
                "status": "error",
                "error": str(e),
            })
    
    # Save results
    results_path = Path("outputs/char_consistency_f5_results.json")
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=2))
    print(f"\n✅ Results saved to {results_path}")
    
    # Summary
    success_count = sum(1 for r in results["results"] if r["status"] == "success")
    print(f"\n📊 Summary: {success_count}/{len(entries)} successful")
    
    return results


if __name__ == "__main__":
    main()
