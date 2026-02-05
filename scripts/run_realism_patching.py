"""
Realism Patching Workflow - Flux2 Klein 9B

Uses FAL's flux-2/klein/9b/base/edit/lora model without LoRA for image editing.
Replicates ComfyUI settings: cfg=1.0, euler scheduler, 10 steps.

Usage:
    python scripts/run_realism_patching.py
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

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.upload_file_to_azure import load_env as load_azure_env, upload_bytes_to_azure


# Config
SHEET_ID = "1g4vcE4dmxq1SmecRPAwXWvDQMcsZFMWae8lCFdi0vvo"
WORKSHEET_NAME = "Realism Patching"
SERVICE_ACCOUNT_PATH = "/home/ubuntu/.openclaw/workspace/.secrets/google-service-account.json"


def load_env():
    load_dotenv(dotenv_path=Path(".env"), override=False)


def extract_url_from_formula(formula: str) -> str | None:
    if not formula:
        return None
    match = re.search(r'=IMAGE\("([^"]+)"\)', formula)
    return match.group(1) if match else formula


def get_sheet_data() -> list[dict]:
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    
    sheet = gc.open_by_key(SHEET_ID)
    worksheet = sheet.worksheet(WORKSHEET_NAME)
    
    range_data = worksheet.get('A1:B20', value_render_option='FORMULA')
    
    entries = []
    for i, row in enumerate(range_data[1:], start=2):  # Skip header
        if len(row) >= 2 and row[0] and row[1]:
            image_url = extract_url_from_formula(row[0])
            prompt = row[1]
            
            if image_url:
                entries.append({
                    "id": f"realism_{i-1}",
                    "row_number": i,
                    "image_url": image_url,
                    "prompt": prompt,
                })
    
    return entries


def run_klein_edit(
    image_url: str,
    prompt: str,
    fal_key: str,
) -> dict:
    """Run image edit using FAL flux-2/klein/9b (non-LoRA endpoint)."""
    endpoint = "https://fal.run/fal-ai/flux-2/klein/9b/base/edit"
    
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    
    # ComfyUI settings: cfg=1.0, euler, steps=10
    payload = {
        "prompt": prompt,
        "image_urls": [image_url],
        "num_images": 1,
        "output_format": "png",
        "guidance_scale": 1.0,  # cfg from ComfyUI
        "num_inference_steps": 10,  # steps from ComfyUI
    }
    
    response = requests.post(endpoint, headers=headers, json=payload, timeout=300)
    response.raise_for_status()
    return response.json()


def download_image(url: str) -> bytes:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def update_sheet_column(row_number: int, cdn_url: str):
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    
    sheet = gc.open_by_key(SHEET_ID)
    worksheet = sheet.worksheet(WORKSHEET_NAME)
    
    cell = f"D{row_number}"
    formula = f'=IMAGE("{cdn_url}")'
    worksheet.update_acell(cell, formula)


def main():
    print("🦅 RAWClaw - Realism Patching Workflow (Flux2 Klein)", flush=True)
    print("=" * 55, flush=True)
    
    load_env()
    load_azure_env()
    
    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        raise ValueError("Missing FAL_KEY environment variable")
    
    # Read sheet
    print("\n📊 Reading sheet data...", flush=True)
    entries = get_sheet_data()
    print(f"Found {len(entries)} entries to process", flush=True)
    
    # Add header to column C
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SHEET_ID)
    worksheet = sheet.worksheet(WORKSHEET_NAME)
    worksheet.update_acell("D1", "FAL Klein (non-LoRA)")
    
    results = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": "fal-ai/flux-2/klein/9b/base/edit/lora (no lora)",
        "settings": {"guidance_scale": 1.0, "steps": 10},
        "results": [],
    }
    
    for entry in entries:
        print(f"\n🔄 Processing {entry['id']} (row {entry['row_number']})...", flush=True)
        
        try:
            fal_result = run_klein_edit(
                image_url=entry["image_url"],
                prompt=entry["prompt"],
                fal_key=fal_key,
            )
            
            images = fal_result.get("images", [])
            result_image_url = images[0].get("url") if images else None
            
            if not result_image_url:
                raise ValueError("No result image returned from FAL")
            
            # Upload to CDN
            image_bytes = download_image(result_image_url)
            blob_name = f"rawclaw/realism-patching/v2/{entry['id']}.png"
            cdn_url = upload_bytes_to_azure(
                data=image_bytes,
                blob_name=blob_name,
                content_type="image/png",
            )
            print(f"  ✅ Uploaded to CDN", flush=True)
            
            # Update sheet
            update_sheet_column(entry["row_number"], cdn_url)
            print(f"  ✅ Updated sheet row {entry['row_number']}", flush=True)
            
            results["results"].append({
                "id": entry["id"],
                "row_number": entry["row_number"],
                "cdn_url": cdn_url,
                "status": "success",
            })
            
        except Exception as e:
            print(f"  ❌ Error: {e}", flush=True)
            results["results"].append({
                "id": entry["id"],
                "row_number": entry["row_number"],
                "status": "error",
                "error": str(e),
            })
    
    # Save results
    results_path = Path("outputs/realism_patching_results.json")
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=2))
    print(f"\n✅ Results saved to {results_path}", flush=True)
    
    success_count = sum(1 for r in results["results"] if r["status"] == "success")
    print(f"\n📊 Summary: {success_count}/{len(entries)} successful", flush=True)
    
    return results


if __name__ == "__main__":
    main()
