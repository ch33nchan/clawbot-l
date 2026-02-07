#!/usr/bin/env python3
"""
Remove female from images using FAL nano-banana-pro/edit.
Updates Google Sheet with results.

Uses: fal-ai/nano-banana-pro/edit
"""

import os
import sys
import re
import requests
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv('/home/ubuntu/research-agent-workflows/.env')

SHEET_ID = '1g4vcE4dmxq1SmecRPAwXWvDQMcsZFMWae8lCFdi0vvo'
WORKSHEET_NAME = 'Sheet8'
CREDENTIALS_PATH = '/home/ubuntu/.openclaw/workspace/.secrets/google-service-account.json'

NBPRO_ENDPOINT = "https://fal.run/fal-ai/nano-banana-pro/edit"


def get_fal_key() -> str:
    key = os.getenv("FAL_KEY")
    if not key:
        raise ValueError("Missing FAL_KEY environment variable")
    return key


def get_sheet():
    creds = Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID).worksheet(WORKSHEET_NAME)


def extract_url_from_image_formula(formula: str) -> str:
    """Extract URL from =IMAGE("url") formula."""
    if not formula:
        return None
    if formula.startswith('=IMAGE'):
        match = re.search(r'"([^"]+)"', formula)
        return match.group(1) if match else None
    return formula


def run_nbpro_remove_female(image_url: str) -> str:
    """
    Run nano-banana-pro to remove the female from the image.
    
    Returns:
        output_url
    """
    fal_key = get_fal_key()
    
    prompt = "Remove the female person from this image. Keep the background and scene intact. Make the result look natural with no traces of the removed person."
    
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "prompt": prompt,
        "image_urls": [image_url],
        "num_images": 1,
        "output_format": "png",
        "resolution": "1K",
    }
    
    response = requests.post(NBPRO_ENDPOINT, headers=headers, json=payload, timeout=300)
    response.raise_for_status()
    
    result = response.json()
    images = result.get("images", [])
    output_url = images[0].get("url") if images else None
    
    return output_url


def main(num_rows: int = 2):
    print(f"Processing {num_rows} rows...", flush=True)
    print(f"Using model: fal-ai/nano-banana-pro/edit", flush=True)
    
    sheet = get_sheet()
    
    for row in range(2, 2 + num_rows):
        print(f"\n=== Row {row} ===", flush=True)
        
        # Get input image URL
        a_formula = sheet.acell(f'A{row}', value_render_option='FORMULA').value
        input_url = extract_url_from_image_formula(a_formula)
        
        if not input_url:
            print(f"  No input image, skipping", flush=True)
            continue
        
        print(f"  Input: {input_url}", flush=True)
        
        # Run nbpro to remove female
        print(f"  Running nano-banana-pro...", flush=True)
        output_url = run_nbpro_remove_female(input_url)
        print(f"  Output: {output_url}", flush=True)
        
        # Update sheet column B with =IMAGE(output_url)
        sheet.update(values=[[f'=IMAGE("{output_url}")']], range_name=f'B{row}', value_input_option='USER_ENTERED')
        
        print(f"  ✓ Row {row} complete", flush=True)
    
    print(f"\n✅ Done! Processed {num_rows} rows", flush=True)


if __name__ == '__main__':
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    main(num)
