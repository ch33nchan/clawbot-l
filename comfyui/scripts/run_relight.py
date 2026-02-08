#!/usr/bin/env python3
"""
ComfyUI Flux2 Klein Relighting Script

Runs relighting workflow on GPU server and uploads results to Azure CDN.

Usage:
    python run_relight.py --input <image_url_or_path> [--prompt "custom prompt"]
    python run_relight.py --input https://example.com/image.png
    python run_relight.py --input /path/to/local/image.png
"""

import os
import sys
import json
import uuid
import time
import argparse
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlparse

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.upload_file_to_azure import upload_file_to_azure, load_env

# Configuration
GPU_HOST = "ubuntu@54.159.123.145"
GPU_COMFYUI_INPUT = "/home/ubuntu/ComfyUI/input"
GPU_COMFYUI_OUTPUT = "/home/ubuntu/ComfyUI/output"
COMFYUI_API_URL = "http://localhost:4000"
WORKFLOW_PATH = Path(__file__).parent.parent / "workflows" / "flux2_klein_relight.json"

DEFAULT_PROMPT = """Relight the image to remove all existing lighting conditions and replace them with soft outdoor neutral and natural with slightly higher contrast and add depth to the image, uniform illumination. Apply soft, evenly distributed lighting with no directional shadows, no harsh highlights, and no dramatic contrast. Maintain the original identity of all subjects exactly—preserve facial structure, skin tone, proportions, expressions, hair, clothing, and textures. Do not alter pose, camera angle, background geometry, or image composition. Lighting should appear balanced. Ensure consistent exposure across the entire image with realistic depth and make sure to keep the background as it is."""


def run_ssh(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run command on GPU server via SSH."""
    full_cmd = f'ssh -o StrictHostKeyChecking=no {GPU_HOST} "{cmd}"'
    return subprocess.run(full_cmd, shell=True, capture_output=True, text=True, check=check)


def scp_to_gpu(local_path: str, remote_path: str):
    """Copy file to GPU server."""
    cmd = f"scp -o StrictHostKeyChecking=no {local_path} {GPU_HOST}:{remote_path}"
    subprocess.run(cmd, shell=True, check=True)


def scp_from_gpu(remote_path: str, local_path: str):
    """Copy file from GPU server."""
    cmd = f"scp -o StrictHostKeyChecking=no {GPU_HOST}:{remote_path} {local_path}"
    subprocess.run(cmd, shell=True, check=True)


def download_image(url: str, local_path: str):
    """Download image from URL."""
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req) as response:
        with open(local_path, 'wb') as f:
            f.write(response.read())


def queue_prompt(workflow: dict, run_id: str) -> dict:
    """Queue prompt on ComfyUI via SSH by writing JSON to temp file."""
    import tempfile
    
    # Write workflow JSON to local temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"prompt": workflow}, f)
        local_json = f.name
    
    try:
        # Copy JSON to GPU
        remote_json = f"/tmp/workflow_{run_id}.json"
        scp_to_gpu(local_json, remote_json)
        
        # Queue prompt using the JSON file
        cmd = f"curl -s -X POST {COMFYUI_API_URL}/prompt -H 'Content-Type: application/json' -d @{remote_json}"
        result = run_ssh(cmd)
        
        # Cleanup remote JSON
        run_ssh(f"rm -f {remote_json}", check=False)
        
        if result.returncode != 0:
            raise Exception(f"Failed to queue prompt: {result.stderr}")
        
        return json.loads(result.stdout) if result.stdout else {}
    finally:
        os.unlink(local_json)


def wait_for_output(output_prefix: str, timeout: int = 300, settle_time: float = 3.0) -> str:
    """Wait for output file with given prefix, then wait for it to finish writing."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        result = run_ssh(f"ls {GPU_COMFYUI_OUTPUT}/ 2>/dev/null | grep '^{output_prefix}'", check=False)
        
        if result.returncode == 0 and result.stdout.strip():
            files = result.stdout.strip().split('\n')
            # Find the actual image file (not temp files)
            for f in files:
                if f.endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    # Wait for file to finish writing
                    print(f"    File detected, waiting {settle_time}s for write to complete...")
                    time.sleep(settle_time)
                    return f
        
        time.sleep(1)
    
    raise TimeoutError(f"Timeout waiting for output with prefix '{output_prefix}'")


def cleanup_gpu(prefix: str):
    """Clean up files on GPU."""
    run_ssh(f"rm -f {GPU_COMFYUI_INPUT}/{prefix}* {GPU_COMFYUI_OUTPUT}/{prefix}*", check=False)


def run_relight(input_image: str, prompt: str = None, output_prefix: str = None) -> str:
    """
    Run relighting workflow on input image.
    
    Args:
        input_image: URL or local path to input image
        prompt: Custom relighting prompt (optional)
        output_prefix: Custom output prefix (optional)
    
    Returns:
        Azure CDN URL of the output image
    """
    # Generate unique prefix for this run
    run_id = output_prefix or str(uuid.uuid4())[:8]
    input_filename = f"{run_id}_input.png"
    output_prefix_full = f"{run_id}_output_"
    
    print(f"[{run_id}] Starting relighting workflow...")
    
    try:
        # Step 1: Get input image to local temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            local_input = os.path.join(tmpdir, input_filename)
            
            if input_image.startswith(('http://', 'https://')):
                print(f"[{run_id}] Downloading input image...")
                download_image(input_image, local_input)
            else:
                # Local file - copy it
                local_input = input_image
                input_filename = f"{run_id}_{os.path.basename(input_image)}"
            
            # Step 2: Upload input to GPU
            print(f"[{run_id}] Uploading to GPU...")
            scp_to_gpu(local_input, f"{GPU_COMFYUI_INPUT}/{input_filename}")
            
            # Step 3: Load and modify workflow
            print(f"[{run_id}] Preparing workflow...")
            with open(WORKFLOW_PATH) as f:
                workflow = json.load(f)
            
            # Update input image (node 19)
            workflow["19"]["inputs"]["image"] = input_filename
            
            # Update prompt if provided (node 17)
            if prompt:
                workflow["17"]["inputs"]["text"] = prompt
            
            # Update output prefix (node 13)
            workflow["13"]["inputs"]["filename_prefix"] = output_prefix_full
            # Change output path to ComfyUI default output folder
            workflow["13"]["inputs"]["output_path"] = GPU_COMFYUI_OUTPUT
            
            # Step 4: Queue the prompt
            print(f"[{run_id}] Queuing prompt on ComfyUI...")
            queue_result = queue_prompt(workflow, run_id)
            print(f"[{run_id}] Queue response: {queue_result}")
            
            # Step 5: Wait for output
            print(f"[{run_id}] Waiting for output...")
            output_filename = wait_for_output(output_prefix_full, timeout=300)
            print(f"[{run_id}] Output ready: {output_filename}")
            
            # Step 6: Download output from GPU
            local_output = os.path.join(tmpdir, output_filename)
            print(f"[{run_id}] Downloading result...")
            scp_from_gpu(f"{GPU_COMFYUI_OUTPUT}/{output_filename}", local_output)
            
            # Step 7: Upload to Azure CDN
            print(f"[{run_id}] Uploading to Azure CDN...")
            cdn_url = upload_file_to_azure(
                local_path=local_output,
                blob_name=f"comfyui/relight/{output_filename}"
            )
            
            print(f"[{run_id}] ✓ Complete! CDN URL: {cdn_url}")
            return cdn_url
            
    finally:
        # Cleanup
        print(f"[{run_id}] Cleaning up...")
        cleanup_gpu(run_id)


def main():
    parser = argparse.ArgumentParser(description="Run Flux2 Klein relighting on ComfyUI")
    parser.add_argument("--input", "-i", required=True, help="Input image URL or local path")
    parser.add_argument("--prompt", "-p", help="Custom relighting prompt")
    parser.add_argument("--prefix", help="Custom output prefix")
    
    args = parser.parse_args()
    
    # Load environment
    load_env(Path(__file__).parent.parent.parent / ".env")
    
    try:
        cdn_url = run_relight(args.input, args.prompt, args.prefix)
        print(f"\n✓ Output URL: {cdn_url}")
        return 0
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
