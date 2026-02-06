#!/usr/bin/env python3
"""
Update CC-F5-Variations sheet with IMAGE formulas and expression analysis.
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
WORKSHEET_NAME = 'CC-F5-Variations'
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
    
    # Update headers for columns D and E
    sheet.update_cell(1, 4, 'Original Preview')
    sheet.update_cell(1, 5, 'Base Expression')
    print("Headers updated")
    
    for i, entry in enumerate(entries):
        row = i + 2  # Row 2, 3, etc.
        base_url = entry['base_image_url']
        
        print(f"\n[Row {row}] Image: {base_url[:60]}...")
        
        # Column A: Original Image URL
        sheet.update_cell(row, 1, base_url)
        print(f"  Col A: URL added")
        
        # Column D: =IMAGE(url) formula
        formula = f'=IMAGE("{base_url}")'
        sheet.update(values=[[formula]], range_name=f'D{row}', value_input_option='USER_ENTERED')
        print(f"  Col D: IMAGE formula added")
        
        # Column E: Expression analysis
        print(f"  Col E: Analyzing expression...")
        expression = analyze_expression(base_url)
        sheet.update_cell(row, 5, expression)
        print(f"  Col E: {expression[:80]}...")
    
    print(f"\n✅ Updated {len(entries)} rows in CC-F5-Variations sheet")


if __name__ == '__main__':
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    main(num)
