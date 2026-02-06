#!/usr/bin/env python3
"""
CC-F5-Variations: Expression-aware face swap workflow.

1. Extract expression from Column A (Original Image)
2. Build prompt with expression for Klein LoRA edit
3. Run face swap: Input1=Column C (Swapped), Input2=Column B (RefAngle)
4. Output → Column D (Swapped Image 2) as =IMAGE()
5. Column E: Prompt used
6. Column F: FAL Playground link (with Request ID)

Uses: fal-ai/flux-2/klein/9b/base/edit/lora with BFS-Best-Face-Swap LoRA
"""

import os
import sys
import re
import requests
import fal_client
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv('/home/ubuntu/research-agent-workflows/.env')

SHEET_ID = '1g4vcE4dmxq1SmecRPAwXWvDQMcsZFMWae8lCFdi0vvo'
WORKSHEET_NAME = 'CC-F5-Variations'
CREDENTIALS_PATH = '/home/ubuntu/.openclaw/workspace/.secrets/google-service-account.json'

# Klein LoRA edit endpoint
KLEIN_LORA_ENDPOINT = "https://fal.run/fal-ai/flux-2/klein/9b/base/edit/lora"
KLEIN_LORA_URL = "https://huggingface.co/Alissonerdx/BFS-Best-Face-Swap/resolve/main/bfs_head_v1_flux-klein_9b_step3500_rank128.safetensors"
FAL_PLAYGROUND_BASE = "https://fal.ai/models/fal-ai/flux-2/klein/9b/base/edit/lora/playground?requestId="

EXPRESSION_PROMPT = """Analyze the facial expression in this image. Describe concisely:
- Emotion (happy, sad, neutral, surprised, etc.)
- Eye expression and gaze direction
- Mouth position
- Overall mood
Keep it to 2-3 sentences max."""


def get_fal_key() -> str:
    """Get FAL API key from environment."""
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


def run_klein_lora_faceswap(base_image_url: str, face_image_url: str, expression: str) -> tuple[str, str, str]:
    """
    Run Klein LoRA face swap with expression-aware prompt.
    
    Uses fal-ai/flux-2/klein/9b/base/edit/lora with BFS-Best-Face-Swap LoRA.
    
    Args:
        base_image_url: URL of base image (body/scene to keep)
        face_image_url: URL of face image (face to swap in)
        expression: Expression description to include in prompt
        
    Returns:
        (output_url, prompt, playground_link)
    """
    fal_key = get_fal_key()
    
    prompt = f"Apply the face from the second image onto the person in the first image. Keep the pose, clothing, and background from the first image. The face should have {expression}. Make it look natural and realistic."
    
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "prompt": prompt,
        "image_urls": [base_image_url, face_image_url],
        "num_images": 1,
        "output_format": "png",
        "guidance_scale": 5,
        "num_inference_steps": 28,
        "loras": [
            {
                "path": KLEIN_LORA_URL,
                "scale": 1.0
            }
        ]
    }
    
    response = requests.post(KLEIN_LORA_ENDPOINT, headers=headers, json=payload, timeout=300)
    response.raise_for_status()
    
    result = response.json()
    
    # Extract result
    images = result.get("images", [])
    output_url = images[0].get("url") if images else None
    request_id = result.get("request_id", response.headers.get("x-fal-request-id", "N/A"))
    playground_link = f"{FAL_PLAYGROUND_BASE}{request_id}"
    
    return output_url, prompt, playground_link


def main(num_rows: int = 2):
    print(f"Processing {num_rows} rows...", flush=True)
    print(f"Using model: fal-ai/flux-2/klein/9b/base/edit/lora", flush=True)
    print(f"LoRA: {KLEIN_LORA_URL}", flush=True)
    
    sheet = get_sheet()
    
    # Update headers D, E, F
    sheet.update_cell(1, 4, 'Swapped Image 2')
    sheet.update_cell(1, 5, 'Prompt Used')
    sheet.update_cell(1, 6, 'FAL Playground Link')
    print("Headers updated: D=Swapped Image 2, E=Prompt, F=Playground Link", flush=True)
    
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
        
        print(f"  A (Original): {original_url}", flush=True)
        print(f"  B (RefAngle): {ref_angle_url}", flush=True)
        print(f"  C (Swapped):  {swapped_url}", flush=True)
        
        # Step 1: Extract expression from Column A
        print(f"  Extracting expression from A...", flush=True)
        expression = analyze_expression(original_url)
        print(f"  Expression: {expression}", flush=True)
        
        # Step 2: Run face swap using Klein LoRA (C=base, B=face)
        print(f"  Running Klein LoRA swap...", flush=True)
        print(f"    image_urls[0] (base): C", flush=True)
        print(f"    image_urls[1] (face): B", flush=True)
        
        output_url, prompt, playground_link = run_klein_lora_faceswap(swapped_url, ref_angle_url, expression)
        
        print(f"  Playground: {playground_link}", flush=True)
        print(f"  Output: {output_url}", flush=True)
        
        # Step 3: Update sheet
        sheet.update(values=[[f'=IMAGE("{output_url}")']], range_name=f'D{row}', value_input_option='USER_ENTERED')
        sheet.update_cell(row, 5, prompt)
        sheet.update_cell(row, 6, playground_link)
        
        print(f"  ✓ Row {row} complete", flush=True)
    
    print(f"\n✅ Done! Processed {num_rows} rows", flush=True)


if __name__ == '__main__':
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    main(num)
