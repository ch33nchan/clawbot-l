#!/usr/bin/env python3
"""
Batch ComfyUI Sunset Relighting - Process rows from Google Sheet (columns D & E)
"""

import os
import sys
import re
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from comfyui.scripts.run_relight import run_relight
from scripts.upload_file_to_azure import load_env

# Config
SHEET_ID = "1g4vcE4dmxq1SmecRPAwXWvDQMcsZFMWae8lCFdi0vvo"
WORKSHEET_GID = 1293424979
SERVICE_ACCOUNT_PATH = "/home/ubuntu/.openclaw/workspace/.secrets/google-service-account.json"

SUNSET_PROMPT = """Relight the image to remove all existing lighting conditions and replace them with dark orange sunset lighting and add depth to the image, uniform illumination. Apply soft, evenly distributed lighting with no directional shadows, no harsh highlights, and no dramatic contrast. Maintain the original identity of all subjects exactly—preserve facial structure, skin tone, proportions, expressions, hair, clothing, and textures. Do not alter pose, camera angle, background geometry, or image composition. Lighting should appear balanced. Ensure consistent exposure across the entire image with realistic depth and make sure to keep the background as it is."""


def extract_url_from_formula(formula: str) -> str | None:
    if not formula:
        return None
    match = re.search(r'=IMAGE\("([^"]+)"\)', formula)
    return match.group(1) if match else formula


def get_sheet():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH, scopes=scopes)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SHEET_ID)
    
    for ws in sheet.worksheets():
        if ws.id == WORKSHEET_GID:
            return ws
    raise ValueError(f"Worksheet with gid {WORKSHEET_GID} not found")


def update_sheet_cells(worksheet, row: int, prompt: str, cdn_url: str):
    """Update columns D (prompt2) and E (comfyui_output2)."""
    # D = column 4, E = column 5
    worksheet.update_cell(row, 4, prompt)
    formula = f'=IMAGE("{cdn_url}")'
    worksheet.update_cell(row, 5, formula)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True, help="Start row (1-indexed)")
    parser.add_argument("--end", type=int, required=True, help="End row (inclusive)")
    args = parser.parse_args()
    
    print(f"🦅 RAWClaw - Batch ComfyUI SUNSET Relighting", flush=True)
    print(f"Processing rows {args.start} to {args.end}", flush=True)
    print("=" * 50, flush=True)
    
    # Load env
    load_env(Path(__file__).parent.parent.parent / ".env")
    
    # Get worksheet
    worksheet = get_sheet()
    
    # Get data with formulas (columns A-E)
    data = worksheet.get(f'A1:E{args.end + 1}', value_render_option='FORMULA')
    
    success_count = 0
    for row_num in range(args.start, args.end + 1):
        row_idx = row_num - 1  # 0-indexed
        if row_idx >= len(data):
            print(f"\n⚠️ Row {row_num} doesn't exist", flush=True)
            continue
            
        row = data[row_idx]
        if len(row) < 1 or not row[0]:
            print(f"\n⚠️ Row {row_num} missing source image", flush=True)
            continue
        
        # Check if already processed (has column E) - skip check if --force
        # if len(row) >= 5 and row[4]:
        #     print(f"\n⚠️ Row {row_num} already has sunset output, skipping", flush=True)
        #     continue
        
        image_url = extract_url_from_formula(row[0])
        
        if not image_url:
            print(f"\n⚠️ Row {row_num} no image URL", flush=True)
            continue
        
        print(f"\n🌅 Processing row {row_num} (sunset)...", flush=True)
        print(f"   Image: {image_url[:60]}...", flush=True)
        
        try:
            cdn_url = run_relight(image_url, SUNSET_PROMPT)
            
            # Update sheet columns D & E (use FULL prompt, never truncate!)
            update_sheet_cells(worksheet, row_num, SUNSET_PROMPT, cdn_url)
            print(f"   ✅ Updated sheet row {row_num}", flush=True)
            success_count += 1
            
        except Exception as e:
            print(f"   ❌ Error: {e}", flush=True)
    
    print(f"\n📊 Summary: {success_count}/{args.end - args.start + 1} successful", flush=True)


if __name__ == "__main__":
    main()
