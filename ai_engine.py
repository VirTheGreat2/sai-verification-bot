import os
import io
import json
import itertools
from PIL import Image
import google.generativeai as genai
import google.api_core.exceptions
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
    Switches to the next API key in the cycle pool and configures genai.
    Returns the selected API key, or None if no keys are available.
    """
    if not key_pool:
        single_key = os.environ.get("GEMINI_API_KEY")
        if single_key:
            genai.configure(api_key=single_key)
            return single_key
        return None
    next_key = next(key_pool)
    genai.configure(api_key=next_key)
    return next_key

# Configure genai initially with the first key if available
rotate_api_key()

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

def get_active_flash_models() -> List[str]:
    """
    Calls genai.list_models(), filters for models that contain 'flash' in their name
    and support 'generateContent', and sorts them descending.
    Falls back to ['models/gemini-1.5-flash'] on failure.
    """
    try:
        models = []
        for m in genai.list_models():
            name_lower = m.name.lower()
            if "flash" in name_lower and "generateContent" in m.supported_generation_methods:
                models.append(m.name)
        models.sort(reverse=True)
        if not models:
            return ["models/gemini-1.5-flash"]
        return models
    except Exception as e:
        print(f"Error fetching active flash models: {e}")
        return ["models/gemini-1.5-flash"]

def verify_document(image_bytes: bytes) -> dict:
    """
    Verifies the student assessment invoice image using Gemini.
    
    1. Converts image_bytes to a PIL Image.
    2. Loads reference images using load_reference_images().
    3. Builds the payload and runs the verify prompt against Gemini models.
    4. Automatically handles 429 ResourceExhausted errors by rotating the API key.
    5. Cleans and parses the response to return {"verified": bool, "reason": str, "extracted_id": str}.
    """
    try:
        user_image = Image.open(io.BytesIO(image_bytes))
        user_image.load()
    except Exception as e:
        return {
            "verified": False,
            "reason": f"Failed to load user image: {str(e)}",
            "extracted_id": ""
        }
        
    reference_images = load_reference_images()
    
    prompt = (
        "You are an STI College auditor. Verify this Student Assessment Invoice (the final image attached). "
        "Text check: Require STI EDUCATION SERVICES GROUP, INC, Student Name, Student ID, and Academic Term. "
        "Visual check: Match table grid layout and headers against ANY of the provided valid reference images. "
        "Tolerance: Ignore minor camera tilts, subtle blur, warm lighting, CamScanner borders, and fold creases. "
        "Extract the student ID."
    )
    
    payload = []
    for ref_img in reference_images:
        payload.append(ref_img)
    payload.append(user_image)
    payload.append(prompt)
    
    models = get_active_flash_models()
    
    max_retries = max(len(api_keys), 3) if api_keys else 3
    
    for model_name in models:
        for attempt in range(max_retries):
            try:
                model = genai.GenerativeModel(model_name)
                generation_config = genai.GenerationConfig(
                    response_mime_type="application/json"
                )
                
                response = model.generate_content(
                    payload,
                    generation_config=generation_config
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
                return {
                    "verified": bool(parsed_json.get("verified", False)),
                    "reason": str(parsed_json.get("reason", "")),
                    "extracted_id": str(parsed_json.get("extracted_id", ""))
                }
                
            except Exception as e:
                # Check for 429/ResourceExhausted
                is_429 = False
                if isinstance(e, google.api_core.exceptions.ResourceExhausted):
                    is_429 = True
                elif hasattr(e, "code") and getattr(e, "code") == 429:
                    is_429 = True
                elif "429" in str(e) or "ResourceExhausted" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    is_429 = True
                    
                if is_429:
                    print(f"ResourceExhausted (429) on model {model_name}. Rotating API key and retrying...")
                    rotated_key = rotate_api_key()
                    if not rotated_key:
                        break
                    continue
                else:
                    print(f"Error with model {model_name}: {e}")
                    break
                    
    return {
        "verified": False,
        "reason": "Verification failed across all models or api keys.",
        "extracted_id": ""
    }
