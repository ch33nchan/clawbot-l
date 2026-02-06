#!/usr/bin/env python3
"""
CC-F5-Variations: Expression-aware face swap workflow.

1. Extract expression from Column A (Original Image)
2. Build prompt with expression for Klein LoRA
3. Run face swap: Input1=Column C (Swapped), Input2=Column B (RefAngle)
4. Output → Column D (Swapped Image 2) as =IMAGE()
5. Column E: Prompt used
"""

import os
import sys
import re
import fal_client
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv('/home/ubuntu/research-agent-workflows/.env')

SHEET_ID = '1g4vcE4dmxq1SmecRPAwXWvDQMcsZFMWae8lCFdi0vvo'
WORKSHEET_NAME = 'CC-F5-Variations'
CREDENTIALS_PATH = '/home/ubuntu/.openclaw/workspace/.secrets/google-service-account.json'

KLEIN_LORA_URL = "https://huggingface.co/Alissonerdx/BFS-Best-Face-Swap/resolve/main/bfs_head_v1_flux-klein_9b_step3750_rank64.safetensors"

EXPRESSION_PROMPT = """Analyze the facial expression in this image. Describe concisely:
- Emotion (happy, sad, neutral, surprised, etc.)
- Eye expression and gaze direction
- Mouth position
- Overall mood
Keep it to 2-3 sentences max."""


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
    return formula  # Already a URL


def analyze_expression(image_url: str) -> str:
    """Use FAL LLaVA-Next to analyze facial expression."""
    result = fal_client.subscribe(
        "fal-ai/llava-next",
        arguments={
            "image_url": image_url,
            "prompt": EXPRESSION_PROMPT,
            "max_tokens": 150
        }
    )
    return result.get('output', 'neutral expression')


def run_klein_faceswap(base_image_url: str, face_image_url: str, expression: str) -> str:
    """Run Klein LoRA face swap with expression-aware prompt."""
    prompt = f"head_swap: start with Picture 1 as the base image, keeping its body and scene intact. Replace the head with the head from Picture 2. The face should have {expression}. Match skin tone and lighting naturally."
    
    result = fal_client.subscribe(
        "fal-ai/flux-general/image-to-image",
        arguments={
            "image_url": base_image_url,
            "image2_url": face_image_url,
            "prompt": prompt,
            "loras": [{"path": KLEIN_LORA_URL, "scale": 1.0}],
            "image_size": "landscape_16_9",
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
            "strength": 0.85
        }
    )
    
    return result['images'][0]['url'], prompt


def main(num_rows: int = 2):
    print(f"Processing {num_rows} rows...", flush=True)
    
    sheet = get_sheet()
    
    # Update headers D and E
    sheet.update_cell(1, 4, 'Swapped Image 2')
    sheet.update_cell(1, 5, 'Prompt Used')
    print("Headers updated: D=Swapped Image 2, E=Prompt Used", flush=True)
    
    for row in range(2, 2 + num_rows):
        print(f"\n=== Row {row} ===", flush=True)
        
        # Get URLs from formulas
        a_formula = sheet.acell(f'A{row}', value_render_option='FORMULA').value
        b_formula = sheet.acell(f'B{row}', value_render_option='FORMULA').value
        c_formula = sheet.acell(f'C{row}', value_render_option='FORMULA').value
        
        original_url = extract_url_from_image_formula(a_formula)
        ref_angle_url = extract_url_from_image_formula(b_formula)
        swapped_url = extract_url_from_image_formula(c_formula)
        
        if not all([original_url, ref_angle_url, swapped_url]):
            print(f"  Missing data, skipping. A={bool(original_url)}, B={bool(ref_angle_url)}, C={bool(swapped_url)}", flush=True)
            continue
        
        print(f"  A (Original): ...{original_url[-40:]}", flush=True)
        print(f"  B (RefAngle): ...{ref_angle_url[-40:]}", flush=True)
        print(f"  C (Swapped): ...{swapped_url[-40:]}", flush=True)
        
        # Step 1: Extract expression from Column A
        print(f"  Extracting expression from A...", flush=True)
        expression = analyze_expression(original_url)
        print(f"  Expression: {expression[:80]}...", flush=True)
        
        # Step 2: Run face swap (C=base, B=face)
        print(f"  Running Klein LoRA swap (C+B)...", flush=True)
        output_url, prompt = run_klein_faceswap(swapped_url, ref_angle_url, expression)
        print(f"  Output: ...{output_url[-50:]}", flush=True)
        
        # Step 3: Update sheet
        # Column D: =IMAGE(output_url)
        sheet.update(values=[[f'=IMAGE("{output_url}")']], range_name=f'D{row}', value_input_option='USER_ENTERED')
        # Column E: prompt
        sheet.update_cell(row, 5, prompt)
        
        print(f"  ✓ Row {row} complete", flush=True)
    
    print(f"\n✅ Done! Processed {num_rows} rows", flush=True)


if __name__ == '__main__':
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    main(num)
