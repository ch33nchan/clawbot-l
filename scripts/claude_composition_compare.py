"""
Claude Vision Composition Comparison

Compares two images (input and output) to detect if composition is preserved
or if objects/humans have been displaced.
"""

import anthropic
import base64
import httpx
import json
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def encode_image_to_base64(image_path: str) -> str:
    """Read a local image file and return base64 encoded string."""
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def fetch_image_as_base64(url: str) -> tuple[str, str]:
    """Fetch an image from URL and return (base64_data, media_type)."""
    response = httpx.get(url, follow_redirects=True)
    response.raise_for_status()
    
    content_type = response.headers.get("content-type", "image/jpeg")
    if "jpeg" in content_type or "jpg" in content_type:
        media_type = "image/jpeg"
    elif "png" in content_type:
        media_type = "image/png"
    elif "webp" in content_type:
        media_type = "image/webp"
    elif "gif" in content_type:
        media_type = "image/gif"
    else:
        media_type = "image/jpeg"
    
    base64_data = base64.standard_b64encode(response.content).decode("utf-8")
    return base64_data, media_type


def get_image_content(image_source: str) -> dict:
    """
    Get image content block for Claude API.
    Accepts either a local file path or a URL.
    """
    if image_source.startswith(("http://", "https://")):
        base64_data, media_type = fetch_image_as_base64(image_source)
    else:
        base64_data = encode_image_to_base64(image_source)
        ext = Path(image_source).suffix.lower()
        media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", 
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(ext, "image/jpeg")
    
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64_data,
        }
    }


def compare_composition(
    input_image: str,
    output_image: str,
    model: str = "claude-sonnet-4-20250514"
) -> dict:
    """
    Compare composition between input and output images.
    
    Args:
        input_image: Path or URL to the original/input image
        output_image: Path or URL to the processed/output image
        model: Claude model to use
    
    Returns:
        dict with composition analysis
    """
    client = anthropic.Anthropic()
    
    prompt = """You are analyzing two images to determine if the composition has been preserved or if objects/humans have been displaced.

IMAGE 1: Original/Input image
IMAGE 2: Processed/Output image

Analyze and compare:

1. **Human Positions**: Are humans in the same positions? Have they moved, shifted, or been displaced?
2. **Object Positions**: Are objects (furniture, items, background elements) in the same positions?
3. **Scene Layout**: Is the overall scene layout preserved?
4. **Scale/Proportions**: Are sizes and proportions maintained?
5. **Cropping/Framing**: Is the framing the same or has it changed?

Respond in this exact JSON format:
```json
{
    "composition_preserved": true/false,
    "human_displacement": {
        "detected": true/false,
        "description": "Description of any human displacement or 'No displacement detected'"
    },
    "object_displacement": {
        "detected": true/false,
        "description": "Description of any object displacement or 'No displacement detected'"
    },
    "scale_preserved": true/false,
    "framing_preserved": true/false,
    "differences": ["list", "of", "specific", "differences"],
    "similarity_score": <1-10 score where 10 is identical composition>,
    "summary": "One sentence summary of composition comparison"
}
```

Be precise and specific about what has changed or stayed the same."""

    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "IMAGE 1 - INPUT/ORIGINAL:"},
                    get_image_content(input_image),
                    {"type": "text", "text": "IMAGE 2 - OUTPUT/PROCESSED:"},
                    get_image_content(output_image),
                    {"type": "text", "text": prompt},
                ]
            }
        ]
    )
    
    response_text = message.content[0].text
    
    # Extract JSON from response
    json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        json_str = json_match.group(0) if json_match else response_text
    
    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        result = {
            "raw_response": response_text,
            "parse_error": True
        }
    
    return result


def batch_compare_composition(comparisons: list[dict], model: str = "claude-sonnet-4-20250514") -> list[dict]:
    """
    Run multiple composition comparisons.
    
    Args:
        comparisons: List of dicts with keys: input_image, output_image, (optional) id
        model: Claude model to use
    
    Returns:
        List of results with original comparison info + analysis
    """
    results = []
    
    for i, comp in enumerate(comparisons):
        print(f"Comparing {i+1}/{len(comparisons)}...")
        
        try:
            analysis = compare_composition(
                input_image=comp["input_image"],
                output_image=comp["output_image"],
                model=model
            )
            
            result = {
                "id": comp.get("id", i),
                **comp,
                **analysis
            }
        except Exception as e:
            result = {
                "id": comp.get("id", i),
                **comp,
                "error": str(e)
            }
        
        results.append(result)
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 3:
        input_img = sys.argv[1]
        output_img = sys.argv[2]
        
        print("Analyzing composition...")
        result = compare_composition(input_img, output_img)
        
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python claude_composition_compare.py <input_image> <output_image>")
        print("Images can be local paths or URLs")
