#!/usr/bin/env python3
"""
Extract expression info from images using FAL LLaVA-Next.
Updates Google Sheet with expression descriptions.
"""

import os
import sys
import json
import fal_client
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/home/ubuntu/research-agent-workflows/.env')

# Configuration
SHEET_ID = '1g4vcE4dmxq1SmecRPAwXWvDQMcsZFMWae8lCFdi0vvo'
WORKSHEET_NAME = 'Char Consistency F5 Data'
CREDENTIALS_PATH = '/home/ubuntu/.openclaw/workspace/.secrets/google-service-account.json'
DATASET_PATH = '/home/ubuntu/research-agent-workflows/datasets/char_consistency_f5_dataset2.json'

EXPRESSION_PROMPT = """Analyze the facial expression in this image. Describe in detail:
1. Overall emotion (happy, sad, angry, neutral, surprised, etc.)
2. Eye expression (wide, squinting, looking direction, intensity)
3. Mouth position (smiling, frowning, open, closed, teeth showing)
4. Eyebrow position (raised, furrowed, relaxed)
5. Overall mood and energy

Be concise but specific. Format as a single paragraph."""


def get_sheet():
    """Connect to Google Sheet."""
    creds = Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(SHEET_ID)
    return spreadsheet.worksheet(WORKSHEET_NAME)


def analyze_expression(image_url: str) -> str:
    """Use FAL LLaVA-Next to analyze facial expression."""
    try:
        result = fal_client.subscribe(
            "fal-ai/llava-next",
            arguments={
                "image_url": image_url,
                "prompt": EXPRESSION_PROMPT,
                "max_tokens": 300
            }
        )
        return result.get('output', 'No output')
    except Exception as e:
        return f"Error: {str(e)}"


def main(num_rows: int = 2):
    """Process first N rows and update sheet."""
    # Load dataset
    with open(DATASET_PATH, 'r') as f:
        dataset = json.load(f)
    
    entries = dataset['entries'][:num_rows]
    
    print(f"Processing {len(entries)} entries...")
    
    # Get sheet
    sheet = get_sheet()
    
    # Check if Expression column exists, add if not
    headers = sheet.row_values(1)
    if 'Base Expression' not in headers:
        # Add new column headers
        next_col = len(headers) + 1
        sheet.update_cell(1, next_col, 'Base Expression')
        sheet.update_cell(1, next_col + 1, 'Base Image URL')
        headers = sheet.row_values(1)
    
    expr_col = headers.index('Base Expression') + 1
    url_col = headers.index('Base Image URL') + 1
    
    results = []
    
    for entry in entries:
        row_num = entry['row_number']
        base_url = entry['base_image_url']
        entry_id = entry['id']
        
        print(f"\n[{entry_id}] Analyzing: {base_url[:60]}...")
        
        expression = analyze_expression(base_url)
        print(f"  Result: {expression[:100]}...")
        
        # Update sheet
        sheet.update_cell(row_num, url_col, base_url)
        sheet.update_cell(row_num, expr_col, expression)
        
        results.append({
            'id': entry_id,
            'row': row_num,
            'image_url': base_url,
            'expression': expression
        })
    
    print(f"\n✅ Processed {len(results)} images")
    return results


if __name__ == '__main__':
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    main(num)
