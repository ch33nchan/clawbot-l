"""
Claude Vision Image Comparison for Head Swap Quality Analysis

Compares original images with head swap results using Claude's vision capabilities.
"""

import anthropic
import base64
import httpx
import os
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
        media_type = "image/jpeg"  # default
    
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


def compare_head_swap(
    body_image: str,
    face_image: str, 
    result_image: str,
    model: str = "claude-sonnet-4-20250514"
) -> dict:
    """
    Compare head swap result against source images.
    
    Args:
        body_image: Path or URL to the body/base image
        face_image: Path or URL to the face/reference image
        result_image: Path or URL to the head swap result
        model: Claude model to use
    
    Returns:
        dict with scores and analysis
    """
    client = anthropic.Anthropic()
    
    prompt = """You are evaluating a head swap AI result. You're given 3 images:

1. BODY IMAGE (Image 1): The base image whose body should be preserved
2. FACE IMAGE (Image 2): The reference face that should replace the head
3. RESULT IMAGE (Image 3): The AI-generated head swap output

Analyze the result and provide scores from 1-10 for each criterion:

1. **Face Identity Preservation** (1-10): How well does the result preserve the identity/features from the face reference?
2. **Body Preservation** (1-10): How well is the original body, pose, and scene preserved?
3. **Skin Tone Matching** (1-10): How naturally does the face skin tone blend with the body?
4. **Lighting Consistency** (1-10): Does the face lighting match the scene lighting?
5. **Blend Quality** (1-10): How seamless is the neck/edge blending? Any visible artifacts?
6. **Overall Realism** (1-10): How realistic and natural does the final result look?

Respond in this exact JSON format:
```json
{
    "face_identity": <score>,
    "body_preservation": <score>,
    "skin_tone": <score>,
    "lighting": <score>,
    "blend_quality": <score>,
    "overall_realism": <score>,
    "average_score": <average of all scores>,
    "major_issues": ["list", "of", "issues"],
    "strengths": ["list", "of", "strengths"],
    "summary": "One sentence summary of the result quality"
}
```

Be critical but fair. A score of 7+ means good quality, 5-6 is acceptable, below 5 has significant issues."""

    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Image 1 - BODY IMAGE (base):"},
                    get_image_content(body_image),
                    {"type": "text", "text": "Image 2 - FACE IMAGE (reference):"},
                    get_image_content(face_image),
                    {"type": "text", "text": "Image 3 - RESULT IMAGE (head swap output):"},
                    get_image_content(result_image),
                    {"type": "text", "text": prompt},
                ]
            }
        ]
    )
    
    # Parse the JSON response
    response_text = message.content[0].text
    
    # Extract JSON from response (handle markdown code blocks)
    import json
    import re
    
    json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON
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


def batch_compare(comparisons: list[dict], model: str = "claude-sonnet-4-20250514") -> list[dict]:
    """
    Run multiple comparisons.
    
    Args:
        comparisons: List of dicts with keys: body_image, face_image, result_image, (optional) id
        model: Claude model to use
    
    Returns:
        List of results with original comparison info + scores
    """
    results = []
    
    for i, comp in enumerate(comparisons):
        print(f"Comparing {i+1}/{len(comparisons)}...")
        
        try:
            scores = compare_head_swap(
                body_image=comp["body_image"],
                face_image=comp["face_image"],
                result_image=comp["result_image"],
                model=model
            )
            
            result = {
                "id": comp.get("id", i),
                **comp,
                **scores
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
    # Example usage
    import sys
    
    if len(sys.argv) == 4:
        body_img = sys.argv[1]
        face_img = sys.argv[2]
        result_img = sys.argv[3]
        
        print("Analyzing head swap quality...")
        result = compare_head_swap(body_img, face_img, result_img)
        
        import json
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python claude_vision_compare.py <body_image> <face_image> <result_image>")
        print("Images can be local paths or URLs")
