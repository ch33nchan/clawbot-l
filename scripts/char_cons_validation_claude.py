#!/usr/bin/env python3
"""
Character Consistency Validation using Claude Vision

Compares char ref image with output image to check if the character
is consistent (same person). Results go in column D of the sheet.
"""

import os
import re
import io
import base64
import requests
from PIL import Image
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import anthropic

load_dotenv()

# Config
SHEET_ID = '1g4vcE4dmxq1SmecRPAwXWvDQMcsZFMWae8lCFdi0vvo'
SHEET_NAME = 'Char Cons Validation'
CREDS_PATH = '/home/ubuntu/.openclaw/workspace/.secrets/google-service-account.json'
MAX_IMAGE_SIZE = 1024  # Max width/height


def extract_url_from_formula(formula: str) -> str:
    """Extract URL from =IMAGE("url") formula."""
    match = re.search(r'=IMAGE\("([^"]+)"\)', formula)
    return match.group(1) if match else formula


def download_and_resize_image(url: str, max_size: int = MAX_IMAGE_SIZE) -> tuple[bytes, tuple[int, int], tuple[int, int]]:
    """
    Download image, resize if needed, return as base64.
    Returns: (base64_bytes, original_size, resized_size)
    """
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    
    img = Image.open(io.BytesIO(response.content))
    original_size = img.size
    
    # Convert to RGB if needed (for PNG with alpha)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    
    # Resize if larger than max_size
    if img.width > max_size or img.height > max_size:
        ratio = min(max_size / img.width, max_size / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    
    resized_size = img.size
    
    # Convert to JPEG bytes
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    return buffer.getvalue(), original_size, resized_size


def validate_character_consistency(client: anthropic.Anthropic, ref_image_b64: str, output_image_b64: str) -> tuple[str, dict]:
    """
    Use Claude to compare two images for character consistency.
    Returns: (result "Yes"/"No", usage_dict)
    """
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Compare these two images. Image 1 is a character reference. Image 2 is an output that should show the same character. Are they the same person (character consistency maintained)? Reply with ONLY 'Yes' or 'No'."
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": ref_image_b64
                        }
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": output_image_b64
                        }
                    }
                ]
            }
        ]
    )
    
    result = message.content[0].text.strip()
    # Normalize to Yes/No
    if result.lower().startswith('yes'):
        result = 'Yes'
    elif result.lower().startswith('no'):
        result = 'No'
    
    usage = {
        'input_tokens': message.usage.input_tokens,
        'output_tokens': message.usage.output_tokens
    }
    
    return result, usage


def main(num_rows: int = 10, dry_run: bool = False):
    """
    Process first num_rows of data.
    
    Args:
        num_rows: Number of data rows to process
        dry_run: If True, don't update sheet, just show what would happen
    """
    # Setup
    creds = Credentials.from_service_account_file(
        CREDS_PATH,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SHEET_ID)
    ws = sheet.worksheet(SHEET_NAME)
    
    client = anthropic.Anthropic()
    
    # Get data (header + num_rows)
    data = ws.get(f'A1:C{num_rows + 1}', value_render_option='FORMULA')
    
    total_input_tokens = 0
    total_output_tokens = 0
    results = []
    
    print(f"Processing {num_rows} rows...\n")
    
    for i, row in enumerate(data[1:], start=2):  # Skip header, start at row 2
        ref_formula = row[0]
        output_formula = row[1]
        human_result = row[2] if len(row) > 2 else ''
        
        ref_url = extract_url_from_formula(ref_formula)
        output_url = extract_url_from_formula(output_formula)
        
        print(f"Row {i}:")
        print(f"  Ref: {ref_url[:60]}...")
        print(f"  Out: {output_url[:60]}...")
        
        # Download and resize images
        ref_bytes, ref_orig, ref_resized = download_and_resize_image(ref_url)
        out_bytes, out_orig, out_resized = download_and_resize_image(output_url)
        
        ref_b64 = base64.standard_b64encode(ref_bytes).decode('utf-8')
        out_b64 = base64.standard_b64encode(out_bytes).decode('utf-8')
        
        print(f"  Ref size: {ref_orig} -> {ref_resized} ({len(ref_bytes)//1024}KB)")
        print(f"  Out size: {out_orig} -> {out_resized} ({len(out_bytes)//1024}KB)")
        
        # Call Claude
        claude_result, usage = validate_character_consistency(client, ref_b64, out_b64)
        
        total_input_tokens += usage['input_tokens']
        total_output_tokens += usage['output_tokens']
        
        match = "✓" if claude_result.lower() == human_result.lower() else "✗"
        print(f"  Claude: {claude_result} | Human: {human_result} | {match}")
        print(f"  Tokens: {usage['input_tokens']} in, {usage['output_tokens']} out")
        print()
        
        results.append({
            'row': i,
            'claude_result': claude_result,
            'human_result': human_result,
            'match': claude_result.lower() == human_result.lower(),
            'usage': usage
        })
    
    # Update sheet with results
    if not dry_run and results:
        # Add header for column D if not present
        ws.update('D1', [['claude result']])
        
        # Update results
        for r in results:
            ws.update(f'D{r["row"]}', [[r['claude_result']]])
        
        print("Sheet updated!")
    
    # Summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"Rows processed: {len(results)}")
    print(f"Matches with human: {sum(1 for r in results if r['match'])}/{len(results)}")
    print(f"\nToken Usage:")
    print(f"  Input tokens:  {total_input_tokens:,}")
    print(f"  Output tokens: {total_output_tokens:,}")
    print(f"  Total tokens:  {total_input_tokens + total_output_tokens:,}")
    
    # Cost estimate (Claude Sonnet pricing: $3/1M input, $15/1M output)
    input_cost = (total_input_tokens / 1_000_000) * 3
    output_cost = (total_output_tokens / 1_000_000) * 15
    total_cost = input_cost + output_cost
    
    print(f"\nCost Estimate (Claude Sonnet):")
    print(f"  Input:  ${input_cost:.4f}")
    print(f"  Output: ${output_cost:.4f}")
    print(f"  Total:  ${total_cost:.4f}")
    
    # Extrapolate to all 54 rows
    per_row_tokens = (total_input_tokens + total_output_tokens) / len(results)
    per_row_cost = total_cost / len(results)
    print(f"\nProjected for all 54 rows:")
    print(f"  Tokens: ~{int(per_row_tokens * 54):,}")
    print(f"  Cost:   ~${per_row_cost * 54:.4f}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--rows', type=int, default=10, help='Number of rows to process')
    parser.add_argument('--dry-run', action='store_true', help='Do not update sheet')
    args = parser.parse_args()
    
    main(num_rows=args.rows, dry_run=args.dry_run)
