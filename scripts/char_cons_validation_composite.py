#!/usr/bin/env python3
"""
Character Consistency Validation - Composite Generator

Creates side-by-side composite images for manual or external vision analysis.
Saves composites to a temp folder and outputs URLs.
"""

import os
import re
import io
import requests
from PIL import Image, ImageDraw, ImageFont
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import sys
sys.path.insert(0, '/home/ubuntu/research-agent-workflows')
from scripts.upload_file_to_azure import upload_bytes_to_azure

load_dotenv()

# Config
SHEET_ID = '1g4vcE4dmxq1SmecRPAwXWvDQMcsZFMWae8lCFdi0vvo'
SHEET_NAME = 'Char Cons Validation'
CREDS_PATH = '/home/ubuntu/.openclaw/workspace/.secrets/google-service-account.json'
MAX_IMAGE_SIZE = 1024  # Max width/height per image


def extract_url_from_formula(formula: str) -> str:
    """Extract URL from =IMAGE("url") formula."""
    match = re.search(r'=IMAGE\("([^"]+)"\)', formula)
    return match.group(1) if match else formula


def download_and_resize_image(url: str, max_size: int = MAX_IMAGE_SIZE) -> Image.Image:
    """Download image and resize if needed."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    
    img = Image.open(io.BytesIO(response.content))
    
    # Convert to RGB if needed
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    
    # Resize if larger than max_size
    if img.width > max_size or img.height > max_size:
        ratio = min(max_size / img.width, max_size / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    
    return img


def create_side_by_side(ref_img: Image.Image, out_img: Image.Image, row_num: int) -> bytes:
    """Create a side-by-side composite with labels."""
    # Make images same height
    max_height = max(ref_img.height, out_img.height)
    
    # Resize to same height maintaining aspect ratio
    if ref_img.height != max_height:
        ratio = max_height / ref_img.height
        ref_img = ref_img.resize((int(ref_img.width * ratio), max_height), Image.Resampling.LANCZOS)
    if out_img.height != max_height:
        ratio = max_height / out_img.height
        out_img = out_img.resize((int(out_img.width * ratio), max_height), Image.Resampling.LANCZOS)
    
    # Create composite with gap
    gap = 20
    label_height = 40
    total_width = ref_img.width + gap + out_img.width
    total_height = max_height + label_height
    
    composite = Image.new('RGB', (total_width, total_height), (255, 255, 255))
    
    # Paste images
    composite.paste(ref_img, (0, label_height))
    composite.paste(out_img, (ref_img.width + gap, label_height))
    
    # Add labels
    draw = ImageDraw.Draw(composite)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except:
        font = ImageFont.load_default()
    
    draw.text((10, 8), f"Row {row_num} - REFERENCE", fill=(0, 100, 0), font=font)
    draw.text((ref_img.width + gap + 10, 8), "OUTPUT", fill=(0, 0, 150), font=font)
    
    # Convert to bytes
    buffer = io.BytesIO()
    composite.save(buffer, format='JPEG', quality=90)
    return buffer.getvalue()


def main(num_rows: int = 10):
    """Generate composites for first num_rows."""
    # Setup
    creds = Credentials.from_service_account_file(
        CREDS_PATH,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SHEET_ID)
    ws = sheet.worksheet(SHEET_NAME)
    
    # Get data
    data = ws.get(f'A1:C{num_rows + 1}', value_render_option='FORMULA')
    
    composites = []
    
    print(f"Generating {num_rows} composite images...\n")
    
    for i, row in enumerate(data[1:], start=2):
        ref_formula = row[0]
        output_formula = row[1]
        human_result = row[2] if len(row) > 2 else ''
        
        ref_url = extract_url_from_formula(ref_formula)
        output_url = extract_url_from_formula(output_formula)
        
        print(f"Row {i}: downloading images...")
        
        # Download and resize
        ref_img = download_and_resize_image(ref_url)
        out_img = download_and_resize_image(output_url)
        
        print(f"  Ref: {ref_img.size}, Out: {out_img.size}")
        
        # Create composite
        composite_bytes = create_side_by_side(ref_img, out_img, i)
        
        # Upload to Azure
        cdn_url = upload_bytes_to_azure(
            data=composite_bytes,
            blob_name=f"char-cons-validation/row_{i}_composite.jpg",
            content_type="image/jpeg"
        )
        
        print(f"  Composite: {cdn_url}")
        print(f"  Human result: {human_result}")
        
        composites.append({
            'row': i,
            'url': cdn_url,
            'human_result': human_result
        })
        print()
    
    # Print summary for easy copy
    print("\n" + "="*60)
    print("COMPOSITE URLS FOR VISION ANALYSIS")
    print("="*60)
    for c in composites:
        print(f"Row {c['row']} (Human: {c['human_result']}): {c['url']}")
    
    return composites


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=int, default=10, help='Number of rows to process')
    args = parser.parse_args()
    
    main(num_rows=args.rows)
