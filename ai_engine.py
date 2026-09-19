import os
import io
import json
import itertools
from PIL import Image
from google import genai
from google.genai import types, errors
from typing import List, Optional, Tuple, Any

def load_env_keys(file_path: str = ".env") -> List[str]:
    """
    Loads GEMINI_API_KEYS from .env or reference_images/.env.
    Splits the keys by comma and returns them as a list.
    """
    paths_to_try = [file_path, "reference_images/.env", "../reference_images/.env"]
    for path in paths_to_try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if "=" in line:
                            k, v = line.split("=", 1)
                            if k.strip() == "GEMINI_API_KEYS":
                                val = v.strip().strip('"').strip("'")
                                return [key.strip() for key in val.split(",") if key.strip()]
    
    # Fallback to os.environ
    env_val = os.environ.get("GEMINI_API_KEYS")
    if env_val:
        return [key.strip() for key in env_val.split(",") if key.strip()]
    return []

# Initialize API Keys pool
api_keys = load_env_keys()
key_pool = itertools.cycle(api_keys) if api_keys else None

def rotate_api_key() -> Optional[str]:
    """
    Switches to the next API key in the cycle pool and returns it.
    Returns the selected API key, or None if no keys are available.
    """
    if not key_pool:
        single_key = os.environ.get("GEMINI_API_KEY")
        if single_key:
            return single_key
        return None
    next_key = next(key_pool)
    return next_key

def load_reference_images(folder_path: str = "reference_images") -> List[Image.Image]:
    """
    Scans the directory for valid images (.jpg, .jpeg, .png, .webp),
    converts them to PIL Image objects, and returns them in a list.
    Returns an empty list if the folder is missing or empty.
    """
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return []
        
    valid_exts = {".jpg", ".jpeg", ".png", ".webp"}
    images = []
    try:
        for filename in sorted(os.listdir(folder_path)):
            ext = os.path.splitext(filename)[1].lower()
            if ext in valid_exts:
                img_path = os.path.join(folder_path, filename)
                try:
                    img = Image.open(img_path)
                    img.load()
                    images.append(img)
                except Exception as e:
                    print(f"Error loading reference image {img_path}: {e}")
    except Exception as e:
        print(f"Error scanning folder {folder_path}: {e}")
        
    return images

def get_active_flash_models(client: Optional[genai.Client] = None) -> List[str]:
    """
    Calls client.models.list(), filters for models that contain 'flash' in their name
    and support 'generateContent'.
    Returns a list of available flash models.
    Falls back to ['gemini-2.5-flash'] or default chain on failure.
    """
    default_fallback = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-flash"]
    try:
        if client is None:
            current_key = rotate_api_key()
            if current_key:
                client = genai.Client(api_key=current_key)
            else:
                client = genai.Client()

        discovered_models = []
        for m in client.models.list():
            name_lower = m.name.lower()
            actions = getattr(m, "supported_actions", None)
            if actions is None:
                actions = getattr(m, "supported_generation_methods", None) or []
            is_generate = "generateContent" in actions or "generate_content" in actions or any("generatecontent" in str(a).lower() for a in actions)
            if "flash" in name_lower and is_generate:
                discovered_models.append(m.name)

        if not discovered_models:
            return default_fallback

        discovered_models.sort(reverse=True)
        return discovered_models
    except Exception as e:
        print(f"Error fetching active flash models: {e}")
        return default_fallback

def optimize_image(image_bytes: bytes) -> Optional[bytes]:
    """
    Optimizes an image's size, format, and resolution for safe API transport and server uploads.
    - Downscales to fit within 2048x2048 while preserving aspect ratio.
    - Converts color modes to RGB.
    - Saves as JPEG at 85% quality.
    - Returns None if invalid or corrupted.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception as e:
        print(f"Failed to identify or load image: {e}")
        return None

    try:
        # Convert RGBA/P to RGB
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        # Downscale maximum maintaining aspect ratio
        img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        
        # Compress and save as JPEG
        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=85)
        return out_buf.getvalue()
    except Exception as e:
        print(f"Error optimizing image: {e}")
        return None

def verify_document(image_bytes: bytes) -> dict:
    """
    Verifies the student assessment invoice image using Gemini.
    
    1. Converts image_bytes to PIL Image to validate format.
    2. Loads reference images.
    3. Builds payload and runs verification prompt against Gemini Flash models.
    4. Smart cascading fallback: automatically handles 429 ResourceExhausted errors by
       rotating API key and cascading across Flash models.
    5. Cleans and parses JSON response schema: {"status": "PASS"|"FAIL", "student_id": string|null, "reason": string}.
    """
    try:
        user_image = Image.open(io.BytesIO(image_bytes))
        user_image.load()
    except Exception as e:
        return {
            "verified": False,
            "status": "FAIL",
            "reason": f"Failed to load user image: {str(e)}",
            "extracted_id": "",
            "student_id": None
        }
        
    reference_images = load_reference_images()
    
    prompt = (
        "You are an STI College auditor. Verify this Student Assessment Invoice (the final image attached). "
        "Text check: Require STI EDUCATION SERVICES GROUP, INC, Student Name, Student ID, and Academic Term. "
        "Visual check: Match table grid layout and headers against ANY of the provided valid reference images. "
        "Tolerance: Ignore minor camera tilts, subtle blur, warm lighting, CamScanner borders, and fold creases. "
        "Extract the student ID. "
        "Return ONLY a JSON object matching this schema: {\"status\": \"PASS\"|\"FAIL\", \"student_id\": \"<extracted_id_or_null>\", \"reason\": \"<explanation>\"}"
    )
    
    # Downscale user image to safe JPEG bytes
    opt_bytes = optimize_image(image_bytes) or image_bytes
    user_part = types.Part.from_bytes(data=opt_bytes, mime_type="image/jpeg")

    payload = []
    for ref_img in reference_images:
        payload.append(ref_img)
    payload.append(user_part)
    payload.append(prompt)
    
    current_key = rotate_api_key()
    if current_key:
        client = genai.Client(api_key=current_key)
    else:
        client = genai.Client()

    models = get_active_flash_models(client)
    max_retries = max(len(api_keys), 3) if api_keys else 3

    for model_name in models:
        for attempt in range(max_retries):
            try:
                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0
                )
                response = client.models.generate_content(
                    model=model_name,
                    contents=payload,
                    config=config
                )
                
                text_content = response.text
                if not text_content:
                    raise ValueError("Empty response from Gemini API.")
                
                cleaned_text = text_content.strip()
                if cleaned_text.startswith("```"):
                    lines = cleaned_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    cleaned_text = "\n".join(lines).strip()
                
                parsed_json = json.loads(cleaned_text)
                
                status = str(parsed_json.get("status", "")).upper()
                verified = bool(parsed_json.get("verified", False)) or (status == "PASS")
                extracted_id = str(parsed_json.get("extracted_id") or parsed_json.get("student_id") or "").strip()
                if extracted_id.lower() in ("null", "none"):
                    extracted_id = ""
                reason = str(parsed_json.get("reason", ""))
                
                return {
                    "verified": verified,
                    "status": "PASS" if verified else "FAIL",
                    "reason": reason,
                    "extracted_id": extracted_id,
                    "student_id": extracted_id if extracted_id else None
                }
                
            except Exception as e:
                is_429 = False
                if isinstance(e, errors.APIError):
                    if getattr(e, "code", None) == 429 or "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "ResourceExhausted" in str(e):
                        is_429 = True
                elif hasattr(e, "code") and getattr(e, "code") == 429:
                    is_429 = True
                elif "429" in str(e) or "ResourceExhausted" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    is_429 = True
                    
                if is_429:
                    print(f"ResourceExhausted (429) on model {model_name}. Rotating API key and retrying...")
                    next_key = rotate_api_key()
                    if next_key:
                        client = genai.Client(api_key=next_key)
                    continue
                else:
                    print(f"Error with model {model_name}: {e}")
                    break
                    
    return {
        "verified": False,
        "status": "FAIL",
        "reason": "Verification failed across all models or api keys.",
        "extracted_id": "",
        "student_id": None
    }
