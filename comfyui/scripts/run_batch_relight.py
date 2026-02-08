#!/usr/bin/env python3
"""
Batch ComfyUI Relighting - Process rows from Google Sheet
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


def update_sheet_cell(worksheet, row: int, col: int, cdn_url: str):
    formula = f'=IMAGE("{cdn_url}")'
    worksheet.update_cell(row, col, formula)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True, help="Start row (1-indexed)")
    parser.add_argument("--end", type=int, required=True, help="End row (inclusive)")
    args = parser.parse_args()
    
    print(f"🦅 RAWClaw - Batch ComfyUI Relighting", flush=True)
    print(f"Processing rows {args.start} to {args.end}", flush=True)
    print("=" * 50, flush=True)
    
    # Load env
    load_env(Path(__file__).parent.parent.parent / ".env")
    
    # Get worksheet
    worksheet = get_sheet()
    
    # Get data with formulas
    data = worksheet.get(f'A1:C{args.end + 1}', value_render_option='FORMULA')
    
    success_count = 0
    for row_num in range(args.start, args.end + 1):
        row_idx = row_num - 1  # 0-indexed
        if row_idx >= len(data):
            print(f"\n⚠️ Row {row_num} doesn't exist", flush=True)
            continue
            
        row = data[row_idx]
        if len(row) < 2:
            print(f"\n⚠️ Row {row_num} missing data", flush=True)
            continue
        
        # Check if already processed (has column C)
        if len(row) >= 3 and row[2]:
            print(f"\n⚠️ Row {row_num} already processed, skipping", flush=True)
            continue
        
        image_url = extract_url_from_formula(row[0])
        prompt = row[1] if len(row) > 1 else None
        
        if not image_url:
            print(f"\n⚠️ Row {row_num} no image URL", flush=True)
            continue
        
        print(f"\n🔄 Processing row {row_num}...", flush=True)
        print(f"   Image: {image_url[:60]}...", flush=True)
        
        try:
            cdn_url = run_relight(image_url, prompt)
            
            # Update sheet column C
            update_sheet_cell(worksheet, row_num, 3, cdn_url)
            print(f"   ✅ Updated sheet row {row_num}", flush=True)
            success_count += 1
            
        except Exception as e:
            print(f"   ❌ Error: {e}", flush=True)
    
    print(f"\n📊 Summary: {success_count}/{args.end - args.start + 1} successful", flush=True)


if __name__ == "__main__":
    main()
