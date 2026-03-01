from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import tempfile
import os
import json
import re
from typing import Optional, Dict, Any
import asyncio
from pathlib import Path
import uuid
import time
import pickle
import numpy as np

# For image processing
from PIL import Image
import base64
import io
import cv2

# For LLM integration (using OpenAI as example)
import openai
from openai import OpenAI
from llm_guidance import generate_and_save_guidance

# For TTS (using Azure Speech Services as example)
import azure.cognitiveservices.speech as speechsdk

# Environment variables
from dotenv import load_dotenv
load_dotenv()

# Import Tobii eye tracking service
from tobii_eye_tracking_service import get_tobii_eye_tracking_service

app = FastAPI(
    title="GazeStory Lab - Child Reading Assistant",
    description="AI-powered reading assistant for children's picture books",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Allow frontend origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Create necessary directories
TEMP_DIR = Path("temp_files")
STATIC_DIR = Path("static")
TEMP_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
(
    STATIC_DIR / "crops"
).mkdir(exist_ok=True)
AOI_DIR = Path("gaze/question")
AOI_DIR.mkdir(parents=True, exist_ok=True)
RESPONSES_DIR = Path("responses/question")
RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
ASSISTANT_DIR = Path("../animated_assistant")
ASSISTANT_DIR.mkdir(exist_ok=True)

# Child-specific folder helpers
def _safe_child_dir(child_name: Optional[str]) -> str:
    try:
        s = (child_name or "").strip()
        if not s:
            return "default"
        import re as _re
        s = _re.sub(r"[^A-Za-z0-9_\-]", "_", s)
        return s or "default"
    except Exception:
        return "default"

def _freeze_key(image_name: str, child_name: Optional[str]) -> str:
    return f"{image_name}|{_safe_child_dir(child_name)}"

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/pictures", StaticFiles(directory="../pictures/question"), name="pictures")
app.mount("/storytelling-pictures", StaticFiles(directory="../pictures/storytelling"), name="storytelling-pictures")
app.mount("/segmented_pictures", StaticFiles(directory="segmented_pictures/question"), name="segmented_pictures")
app.mount("/responses/question", StaticFiles(directory="responses/question"), name="responses_question")
app.mount("/responses", StaticFiles(directory="responses"), name="responses")
app.mount("/gaze", StaticFiles(directory="gaze/question"), name="gaze")
app.mount("/assistant", StaticFiles(directory=str(ASSISTANT_DIR)), name="assistant")

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Azure Speech configuration
speech_config = speechsdk.SpeechConfig(
    subscription=os.getenv("AZURE_SPEECH_KEY"),
    region=os.getenv("AZURE_SPEECH_REGION")
)


class NarrationService:
    """Service for generating narrations from images using multimodal LLM"""
    
    @staticmethod
    async def analyze_image(image_data: bytes, age: int = 5, language: str = "en") -> Dict[str, Any]:
        """Analyze image and generate child-friendly narration"""
        
        # Convert image to base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        # Age-appropriate prompts
        age_prompts = {
            3: "very simple words, 1-2 sentences",
            4: "simple words, 2-3 sentences", 
            5: "easy words, 3-4 sentences",
            6: "basic vocabulary, 4-5 sentences",
            7: "elementary vocabulary, 5-6 sentences"
        }
        
        complexity = age_prompts.get(age, "simple words, 3-4 sentences")
        
        prompt = f"""
        You are a friendly children's reading assistant. Look at this picture book page and create a warm, engaging narration for a {age}-year-old child.

        Guidelines:
        - Use {complexity}
        - Be encouraging and positive
        - Focus on what's happening in the picture
        - Use child-friendly language
        - Make it sound like a caring adult reading to a child
        - Include emotions and descriptive words that help imagination
        - Keep it safe and appropriate

        Return your response as JSON with this exact structure:
        {{
            "narration_text": "Your warm, engaging narration here"
        }}

        Language: {language}
        """
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=300,
                temperature=0.7
            )
            
            # Parse the JSON response
            content = response.choices[0].message.content
            # Extract JSON from the response (in case there's extra text)
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                raise ValueError("No JSON found in response")
                
        except Exception as e:
            print(f"Error in image analysis: {e}")
            # Fallback response
            return {
                "narration_text": "What a wonderful picture! I can see so many interesting things happening here. Let's look closely together and imagine the story!"
            }
    
    @staticmethod
    async def analyze_multiple_images(image_data_list: list, filenames: list, age: int = 5, language: str = "en") -> Dict[str, Any]:
        """Analyze multiple images and generate a connected story"""
        
        # Convert all images to base64
        image_content = []
        for i, image_data in enumerate(image_data_list):
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            image_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }
            })
        
        # Age-appropriate prompts for longer stories
        age_prompts = {
            3: "very simple words, 3-4 sentences total",
            4: "simple words, 4-6 sentences total", 
            5: "easy words, 6-8 sentences total",
            6: "basic vocabulary, 8-10 sentences total",
            7: "elementary vocabulary, 10-12 sentences total"
        }
        
        complexity = age_prompts.get(age, "easy words, 6-8 sentences total")
        image_count = len(image_data_list)
        
        prompt = f"""
        You are a friendly children's reading assistant. Look at these {image_count} picture book pages and create a warm, engaging story that connects all the images for a {age}-year-old child.

        Guidelines:
        - Use {complexity}
        - Create a flowing story that connects all {image_count} images
        - Be encouraging and positive
        - Focus on what's happening across all the pictures
        - Use child-friendly language
        - Make it sound like a caring adult telling a complete story
        - Include emotions and descriptive words that help imagination
        - Keep it safe and appropriate
        - Make the story longer and more detailed since there are multiple images
        - Connect the scenes logically to create one cohesive narrative

        Return your response as JSON with this exact structure:
        {{
            "narration_text": "Your warm, engaging connected story here (longer due to multiple images)"
        }}

        Language: {language}
        """
        
        try:
            # Create message content with text prompt and all images
            message_content = [{"type": "text", "text": prompt}] + image_content
            
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": message_content
                    }
                ],
                max_tokens=500 + (image_count * 100),  # More tokens for multiple images
                temperature=0.7
            )
            
            # Parse the JSON response
            content = response.choices[0].message.content
            # Extract JSON from the response (in case there's extra text)
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                raise ValueError("No JSON found in response")
                
        except Exception as e:
            print(f"Error in multiple image analysis: {e}")
            # Fallback response for multiple images
            return {
                "narration_text": f"What an amazing collection of {image_count} pictures! Each one tells part of a wonderful story. I can see so many exciting things happening across all these images. Together, they create a magical adventure that we can explore and imagine together!"
            }


class SafetyFilter:
    """Content safety and length filtering"""
    
    @staticmethod
    def filter_content(text: str, max_words: int = 100) -> str:
        """Apply safety and length filters"""
        
        # Remove potentially unsafe content
        unsafe_patterns = [
            r'\b(scary|frightening|dangerous|violent|hurt|pain|death|die|kill)\b',
            # Add more patterns as needed
        ]
        
        filtered_text = text
        for pattern in unsafe_patterns:
            filtered_text = re.sub(pattern, '', filtered_text, flags=re.IGNORECASE)
        
        # Length limiting
        words = filtered_text.split()
        if len(words) > max_words:
            filtered_text = ' '.join(words[:max_words]) + "..."
        
        return filtered_text.strip()


class TTSService:
    """Text-to-Speech service using Azure Speech Services"""
    
    @staticmethod
    async def synthesize_speech(text: str, language: str = "en-US", voice_override: Optional[str] = None) -> str:
        """Convert text to speech and return file path"""
        
        try:
            # Configure voice based on language
            voice_map = {
                "en-US": "en-US-AnaNeural",
                "en-GB": "en-GB-MiaNeural",
                "en-AU": "en-AU-NatashaNeural",
                "es-ES": "es-ES-ElviraNeural",
                "fr-FR": "fr-FR-DeniseNeural",
            }
            # If an explicit Azure voice name is provided, prefer it
            voice_name = (voice_override or voice_map.get(language) or "en-US-AnaNeural")
            
            # Create SSML for more natural speech
            ssml = f"""
            <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{language}">
                <voice name="{voice_name}">
                    <prosody rate="0.9" pitch="+10%">
                        {text}
                    </prosody>
                </voice>
            </speak>
            """
            
            # Generate unique filename
            audio_filename = f"narration_{uuid.uuid4().hex}.wav"
            audio_path = STATIC_DIR / audio_filename
            
            # Configure audio output
            audio_config = speechsdk.audio.AudioOutputConfig(filename=str(audio_path))
            speech_config.speech_synthesis_voice_name = voice_name
            
            # Create synthesizer and synthesize
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config, 
                audio_config=audio_config
            )
            
            print(f"[TTS] Using voice: {voice_name} for language: {language}")

            result = synthesizer.speak_ssml_async(ssml).get()
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                return f"/static/{audio_filename}"
            else:
                raise Exception(f"Speech synthesis failed: {result.reason}")
                
        except Exception as e:
            print(f"TTS Error: {e}")
            # Return None if TTS fails - client will use text fallback
            return None


@app.post("/tts/speak")
async def tts_speak(
    text: str = Form(...),
    language: str = Form("en-US"),
    voice: Optional[str] = Form(None)
):
    try:
        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="text is required")
        audio_url = await TTSService.synthesize_speech(text.strip(), language, voice_override=voice)
        if not audio_url:
            raise HTTPException(status_code=500, detail="TTS synthesis failed")
        return {"audio_url": audio_url}
    except HTTPException:
        raise
    except Exception as e:
        print(f"/tts/speak error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =====================
# Cropping functionality
# =====================

_segmentation_cache: Dict[str, Dict[str, Any]] = {}
_image_cache: Dict[str, np.ndarray] = {}
_recent_crops: Dict[str, float] = {}
_aoi_last_index: Dict[str, int] = {}
_label_map_cache: Dict[str, np.ndarray] = {}
_label_mapping_cache: Dict[str, Dict[int, Dict[str, Any]]] = {}
_aoi_freeze: Dict[str, bool] = {}

# Step 1: Request cancellation system
_active_guidance_requests: Dict[str, str] = {}  # image_key -> request_id
_guidance_cancellation_flags: Dict[str, bool] = {}  # request_id -> bool


def cancel_existing_guidance(image_filename: str, child_name: Optional[str] = None) -> Optional[str]:
    """Cancel any existing guidance generation for this image"""
    image_name = Path(image_filename).stem
    key = _freeze_key(image_name, child_name)
    
    if key in _active_guidance_requests:
        old_request_id = _active_guidance_requests[key]
        _guidance_cancellation_flags[old_request_id] = True
        print(f"🚫 [STEP1] Cancelled guidance request {old_request_id} for {image_filename}")
        return old_request_id
    
    return None


def is_request_cancelled(request_id: str) -> bool:
    """Check if a request has been cancelled"""
    return _guidance_cancellation_flags.get(request_id, False)


def register_guidance_request(image_filename: str, request_id: str, child_name: Optional[str] = None) -> None:
    """Register a new guidance request, cancelling any existing one"""
    # Cancel existing request first
    cancel_existing_guidance(image_filename, child_name)
    
    # Register new request
    image_name = Path(image_filename).stem
    key = _freeze_key(image_name, child_name)
    _active_guidance_requests[key] = request_id
    _guidance_cancellation_flags[request_id] = False
    print(f"✅ [STEP1] Registered guidance request {request_id} for {image_filename}")


def cleanup_guidance_request(request_id: str) -> None:
    """Clean up completed or cancelled guidance request"""
    if request_id in _guidance_cancellation_flags:
        del _guidance_cancellation_flags[request_id]
    
    # Remove from active requests
    for key, active_id in list(_active_guidance_requests.items()):
        if active_id == request_id:
            del _active_guidance_requests[key]
            break
    
    print(f"🧹 [STEP1] Cleaned up guidance request {request_id}")


def _load_segmentation_objects(image_name: str) -> Dict[str, Any]:
    if image_name in _segmentation_cache:
        return _segmentation_cache[image_name]
    seg_path = Path("segmented_objects") / f"{image_name}_segmentation.pkl"
    if not seg_path.exists():
        raise HTTPException(status_code=404, detail=f"Segmentation not found for {image_name}")
    with open(seg_path, 'rb') as f:
        objects = pickle.load(f)
    _segmentation_cache[image_name] = objects
    return objects


def _load_source_image(image_filename: str) -> np.ndarray:
    if image_filename in _image_cache:
        return _image_cache[image_filename]
    img_path = Path("../pictures/question") / image_filename
    if not img_path.exists():
        raise HTTPException(status_code=404, detail=f"Source image not found: {image_filename}")
    img = cv2.imread(str(img_path))
    if img is None:
        raise HTTPException(status_code=500, detail="Failed to load source image")
    _image_cache[image_filename] = img
    return img


def _load_label_assets(image_name: str) -> tuple[np.ndarray, Dict[int, Dict[str, Any]]]:
    """Load (and cache) the label map PNG and JSON index->metadata mapping."""
    if image_name in _label_map_cache and image_name in _label_mapping_cache:
        return _label_map_cache[image_name], _label_mapping_cache[image_name]

    labels_png_path = Path("segmented_pictures/question") / f"{image_name}_labels.png"
    labels_json_path = Path("segmented_pictures/question") / f"{image_name}_labels.json"
    if not labels_png_path.exists() or not labels_json_path.exists():
        raise HTTPException(status_code=404, detail="Label assets not found")

    label_map = cv2.imread(str(labels_png_path), cv2.IMREAD_GRAYSCALE)
    if label_map is None:
        raise HTTPException(status_code=500, detail="Failed to load label map PNG")

    with open(labels_json_path, 'r') as f:
        labels = json.load(f)

    index_to_meta: Dict[int, Dict[str, Any]] = {}
    for o in labels.get("objects", []):
        idx = int(o.get("index", 0))
        if idx > 0:
            index_to_meta[idx] = o

    _label_map_cache[image_name] = label_map
    _label_mapping_cache[image_name] = index_to_meta
    return label_map, index_to_meta


def _alpha_masked_crop(image_bgr: np.ndarray, mask: np.ndarray, bbox_xyxy) -> Image.Image:
    x1, y1, x2, y2 = [int(v) for v in bbox_xyxy]
    x1 = max(0, min(image_bgr.shape[1]-1, x1))
    y1 = max(0, min(image_bgr.shape[0]-1, y1))
    x2 = max(0, min(image_bgr.shape[1], x2))
    y2 = max(0, min(image_bgr.shape[0], y2))
    roi = image_bgr[y1:y2, x1:x2]
    roi_mask = mask[y1:y2, x1:x2].astype(np.uint8) * 255
    # Feather edges 1-2 px
    kernel = np.ones((3, 3), np.uint8)
    roi_mask = cv2.morphologyEx(roi_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    alpha = roi_mask
    b, g, r = cv2.split(roi)
    rgba = cv2.merge([r, g, b, alpha])
    pil_img = Image.fromarray(rgba, mode='RGBA')
    # Optional clamp max dimension
    max_dim = 1024
    w, h = pil_img.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1.0:
        pil_img = pil_img.resize((int(w*scale), int(h*scale)), resample=Image.LANCZOS)
    return pil_img


def _save_crop_for_index(image_filename: str, object_index: int, include_alpha: bool = True) -> Optional[str]:
    """Create and save a crop for the given image/index unconditionally. Returns URL or None on failure."""
    try:
        image_name = Path(image_filename).stem
        label_map, index_to_meta = _load_label_assets(image_name)
        obj_meta = index_to_meta.get(int(object_index))
        if obj_meta is None:
            return None
        image_bgr = _load_source_image(image_filename)
        if label_map.shape[0] != image_bgr.shape[0] or label_map.shape[1] != image_bgr.shape[1]:
            label_map = cv2.resize(label_map, (image_bgr.shape[1], image_bgr.shape[0]), interpolation=cv2.INTER_NEAREST)
            _label_map_cache[image_name] = label_map
        mask = (label_map == int(object_index))
        bbox = obj_meta.get("bbox")
        if not bbox or len(bbox) != 4:
            ys, xs = np.where(mask)
            if ys.size == 0 or xs.size == 0:
                return None
            x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)
            bbox = [x1, y1, x2, y2]
        pil_crop = _alpha_masked_crop(image_bgr, mask, bbox) if include_alpha else Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        ts = int(time.time() * 1000)
        object_id = obj_meta.get("object_id", f"idx{int(object_index)}")
        out_name = f"{image_name}_{object_id}_{ts}.png"
        out_path = STATIC_DIR / "crops" / out_name
        pil_crop.save(out_path, format="PNG")
        return f"/static/crops/{out_name}"
    except Exception:
        return None


@app.post("/crops/extract")
async def extract_crop(
    image_filename: str = Form(...),
    object_index: int = Form(...),
    include_alpha: bool = Form(True),
    format: str = Form("png"),
    assistance: str = Form("child"),
    child_name: Optional[str] = Form(None)
):
    """Return a masked crop (PNG with alpha) for a fixated object.

    - image_filename: e.g., "1.jpg"
    - object_index: label index from {image}_labels.png (1..N)
    """
    try:
        if format.lower() != "png":
            raise HTTPException(status_code=400, detail="Only PNG supported")

        image_name = Path(image_filename).stem

        # Dedupe key and cooldown
        key = f"{image_filename}:{object_index}"
        now = time.time()
        last = _recent_crops.get(key, 0)
        if now - last < 1.0:
            raise HTTPException(status_code=429, detail="Too many crops; wait a moment")

        # Load label assets (PNG + JSON)
        label_map, index_to_meta = _load_label_assets(image_name)
        obj_meta = index_to_meta.get(int(object_index))
        if obj_meta is None:
            raise HTTPException(status_code=404, detail="Object index not found")

        # Check AOI cumulative fixation and dedupe per AOI (index)
        aoi_data = _load_aoi_file(image_name, image_filename, assistance=assistance, child_name=child_name)
        objects = aoi_data.get("objects", [])
        aoi_entry = None
        for o in objects:
            if o.get("index") == int(object_index):
                aoi_entry = o
                break
        threshold_ms = 4000
        if aoi_entry is None or int(aoi_entry.get("fixation_duration", 0)) < threshold_ms:
            return {
                "success": False,
                "skipped": True,
                "reason": "duration_threshold_not_met",
                "current_duration_ms": int(aoi_entry.get("fixation_duration", 0)) if aoi_entry else 0,
                "threshold_ms": threshold_ms
            }
        if aoi_entry.get("crop_saved") and aoi_entry.get("crop_url"):
            return {
                "success": True,
                "url": aoi_entry.get("crop_url"),
                "object_id": obj_meta.get("object_id"),
                "bbox": aoi_entry.get("bbox", obj_meta.get("bbox")),
                "area": int(obj_meta.get("area", 0)),
                "already_saved": True
            }

        # Build binary mask from label map
        image_bgr = _load_source_image(image_filename)
        if label_map.shape[0] != image_bgr.shape[0] or label_map.shape[1] != image_bgr.shape[1]:
            label_map = cv2.resize(label_map, (image_bgr.shape[1], image_bgr.shape[0]), interpolation=cv2.INTER_NEAREST)
            _label_map_cache[image_name] = label_map

        mask = (label_map == int(object_index))
        bbox = obj_meta.get("bbox")
        if not bbox or len(bbox) != 4:
            # Fallback: compute bbox from mask
            ys, xs = np.where(mask)
            if ys.size == 0 or xs.size == 0:
                raise HTTPException(status_code=404, detail="Empty mask for object index")
            x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)
            bbox = [x1, y1, x2, y2]

        pil_crop = _alpha_masked_crop(image_bgr, mask, bbox) if include_alpha else Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))

        # Save
        ts = int(now * 1000)
        object_id = obj_meta.get("object_id", f"idx{int(object_index)}")
        out_name = f"{image_name}_{object_id}_{ts}.png"
        out_path = STATIC_DIR / "crops" / out_name
        pil_crop.save(out_path, format="PNG")

        _recent_crops[key] = now

        # Mark AOI as saved and persist
        try:
            if aoi_entry is not None:
                aoi_entry["crop_saved"] = True
                aoi_entry["crop_url"] = f"/static/crops/{out_name}"
                aoi_entry["crop_saved_at"] = int(now * 1000)
                aoi_data["objects"] = objects
                _save_aoi_file(image_name, aoi_data, assistance=assistance, child_name=child_name)
        except Exception as _:
            pass

        return {
            "success": True,
            "url": f"/static/crops/{out_name}",
            "object_id": obj_meta.get("object_id"),
            "bbox": bbox,
            "area": int(obj_meta.get("area", 0))
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Crop error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate crop")


def _aoi_file_paths(image_name: str, assistance: str, child_name: Optional[str] = None):
    """Return AOI/fixtures file paths based on assistance type, not detection mode.

    assistance values:
    - "child" (child-alone)
    - "parent_basic" (parent-child basic assistance)
    - "parent_guided" (parent-child guided assistance)
    """
    safe_assistance = (assistance or "child").lower()
    child_dir = AOI_DIR / _safe_child_dir(child_name)
    child_dir.mkdir(parents=True, exist_ok=True)
    
    # Create separate aoi and fixation subdirectories
    aoi_subdir = child_dir / "aoi"
    fixation_subdir = child_dir / "fixation"
    aoi_subdir.mkdir(parents=True, exist_ok=True)
    fixation_subdir.mkdir(parents=True, exist_ok=True)
    
    aoi_path = aoi_subdir / f"{image_name}_{safe_assistance}_aois.json"
    fix_path = fixation_subdir / f"{image_name}_{safe_assistance}_fixations.json"
    return aoi_path, fix_path


def _load_aoi_file(image_name: str, image_filename: str, assistance: str = "child", child_name: Optional[str] = None) -> Dict[str, Any]:
    aoi_path, _ = _aoi_file_paths(image_name, assistance, child_name)
    if aoi_path.exists():
        with open(aoi_path, 'r') as f:
            try:
                return json.load(f)
            except Exception:
                pass
    return {"image_filename": image_filename, "objects": [], "updated_at": time.time(), "assistance": assistance}


def _save_aoi_file(image_name: str, data: Dict[str, Any], assistance: str = "child", child_name: Optional[str] = None) -> None:
    aoi_path, _ = _aoi_file_paths(image_name, assistance, child_name)
    data["updated_at"] = time.time()
    aoi_path.parent.mkdir(parents=True, exist_ok=True)
    with open(aoi_path, 'w') as f:
        json.dump(data, f, indent=2)


def _append_fixation_event(
    image_name: str,
    image_filename: str,
    object_index: int,
    object_id: str,
    start_ts: int,
    end_ts: int,
    duration_ms: int,
    assistance: str = "child",
    child_name: Optional[str] = None,
    x_coordinate: Optional[float] = None,
    y_coordinate: Optional[float] = None
) -> None:
    _, ev_path = _aoi_file_paths(image_name, assistance, child_name)
    events = []
    if ev_path.exists():
        try:
            with open(ev_path, 'r') as f:
                events = json.load(f)
        except Exception:
            events = []
    
    # Only save essential fixation data with coordinates
    fixation_event = {
        "start_ts": int(start_ts),
        "end_ts": int(end_ts),
        "duration_ms": int(duration_ms)
    }
    
    # Add coordinates if available
    if x_coordinate is not None and y_coordinate is not None:
        fixation_event["x_coordinate"] = float(x_coordinate)
        fixation_event["y_coordinate"] = float(y_coordinate)
    
    events.append(fixation_event)
    ev_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ev_path, 'w') as f:
        json.dump(events, f, indent=2)


# =====================
# AOI Definitions & Overlay
# =====================

def _aoi_defs_path(image_name: str, child_name: Optional[str] = None) -> Path:
    child_dir = AOI_DIR / _safe_child_dir(child_name)
    child_dir.mkdir(parents=True, exist_ok=True)
    return child_dir / f"{image_name}_aoi_defs.json"


def _load_aoi_defs(image_filename: str, child_name: Optional[str] = None) -> Dict[str, Any]:
    image_name = Path(image_filename).stem
    path = _aoi_defs_path(image_name, child_name)
    if path.exists():
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "image_filename": image_filename,
        "version": 1,
        "created_at": int(time.time() * 1000),
        "aois": []
    }


def _save_aoi_defs(image_filename: str, defs_data: Dict[str, Any], child_name: Optional[str] = None) -> None:
    image_name = Path(image_filename).stem
    path = _aoi_defs_path(image_name, child_name)
    defs_data.setdefault("image_filename", image_filename)
    defs_data["updated_at"] = int(time.time() * 1000)
    with open(path, 'w') as f:
        json.dump(defs_data, f, indent=2)


def _compute_aoi_properties(image_filename: str, aoi_defs: Dict[str, Any], child_name: Optional[str] = None) -> Dict[str, Any]:
    image_name = Path(image_filename).stem
    label_map, index_to_meta = _load_label_assets(image_name)
    image_bgr = _load_source_image(image_filename)

    updated_aois = []
    for aoi in aoi_defs.get("aois", []):
        indices = [int(i) for i in aoi.get("indices", []) if int(i) > 0]
        if not indices:
            continue
        mask = np.isin(label_map, indices)
        ys, xs = np.where(mask)
        if ys.size == 0 or xs.size == 0:
            bbox = None
            area = 0
        else:
            x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)
            bbox = [x1, y1, x2, y2]
            area = int(mask.sum())
        name = aoi.get("name") or aoi.get("aoi_id") or f"AOI_{len(updated_aois)+1:03d}"
        aoi_id = aoi.get("aoi_id") or name
        # Add mask_path if a saved mask exists  
        aoi_mask_path = _aoi_mask_path(image_name, aoi_id, child_name)
        updated = {
            "aoi_id": aoi_id,
            "name": name,
            "indices": indices,
            "bbox": bbox,
            "area": area
        }
        if aoi_mask_path.exists():
            updated["mask_path"] = f"/gaze/{image_name}_{aoi_id}_mask.png"
        updated_aois.append(updated)
    aoi_defs["aois"] = updated_aois
    return aoi_defs


def _generate_aoi_overlay(image_filename: str, child_name: Optional[str] = None) -> str:
    image_name = Path(image_filename).stem
    # Load
    aoi_defs = _load_aoi_defs(image_filename, child_name)
    label_map, _ = _load_label_assets(image_name)
    image_bgr = _load_source_image(image_filename).copy()
    h, w = label_map.shape[:2]

    # Colors
    rng = np.random.default_rng(12345)
    colors = rng.integers(0, 255, size=(max(1, len(aoi_defs.get("aois", []))), 3), dtype=np.uint8)

    # Overlay
    overlay = image_bgr.copy()
    border = np.zeros_like(image_bgr)
    for idx, aoi in enumerate(aoi_defs.get("aois", [])):
        indices = [int(i) for i in aoi.get("indices", []) if int(i) > 0]
        if not indices:
            continue
        mask = np.isin(label_map, indices)
        color = tuple(int(c) for c in colors[idx])
        overlay[mask] = (overlay[mask] * 0.4 + np.array(color, dtype=np.uint8) * 0.6).astype(np.uint8)
        # Border from contours
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            cv2.drawContours(border, contours, -1, (255, 255, 255), 2)

    result = cv2.addWeighted(overlay, 0.85, border, 0.15, 0)
    out_path = Path("segmented_pictures/question") / f"{image_name}_aoi_overlay.jpg"
    cv2.imwrite(str(out_path), result)
    return f"/segmented_pictures/{image_name}_aoi_overlay.jpg"


@app.get("/aoi/defs")
async def get_aoi_defs(image_filename: str, child_name: Optional[str] = None):
    defs_data = _load_aoi_defs(image_filename, child_name)
    return defs_data


@app.post("/aoi/defs")
async def save_aoi_defs(payload: Dict[str, Any]):
    image_filename = payload.get("image_filename")
    child_name = payload.get("child_name")
    if not image_filename:
        raise HTTPException(status_code=400, detail="image_filename required")
    aois = payload.get("aois")
    if not isinstance(aois, list):
        raise HTTPException(status_code=400, detail="aois must be a list")
    defs_data = {
        "image_filename": image_filename,
        "version": int(payload.get("version", 1)),
        "created_at": int(payload.get("created_at", int(time.time() * 1000))),
        "aois": aois
    }
    defs_data = _compute_aoi_properties(image_filename, defs_data, child_name)
    _save_aoi_defs(image_filename, defs_data, child_name)
    return {"success": True, "saved": defs_data, "file": f"/gaze/{_safe_child_dir(child_name)}/{Path(image_filename).stem}_aoi_defs.json"}


@app.post("/aoi/overlay")
async def generate_aoi_overlay(image_filename: str = Form(...), child_name: Optional[str] = Form(None)):
    try:
        url = _generate_aoi_overlay(image_filename, child_name)
        return {"success": True, "overlay_url": url}
    except HTTPException:
        raise
    except Exception as e:
        print(f"AOI overlay error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate AOI overlay")


def _aoi_mask_path(image_name: str, aoi_id: str, child_name: Optional[str] = None) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_\-]", "_", aoi_id)
    child_dir = AOI_DIR / _safe_child_dir(child_name)
    child_dir.mkdir(parents=True, exist_ok=True)
    return child_dir / f"{image_name}_{safe_id}_mask.png"


@app.get("/aoi/mask")
async def get_aoi_mask(image_filename: str, aoi_id: str, child_name: Optional[str] = None):
    image_name = Path(image_filename).stem
    path = _aoi_mask_path(image_name, aoi_id, child_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="AOI mask not found")
    return FileResponse(path, media_type="image/png")


@app.post("/aoi/mask/save")
async def save_aoi_mask(
    payload: Optional[Dict[str, Any]] = None,
    image_filename: Optional[str] = Form(None),
    aoi_id: Optional[str] = Form(None),
    mask_png_base64: Optional[str] = Form(None),
    child_name: Optional[str] = Form(None)
):
    # Accept JSON or multipart/form-data
    if payload:
        image_filename = image_filename or payload.get("image_filename")
        aoi_id = aoi_id or payload.get("aoi_id")
        mask_png_base64 = mask_png_base64 or payload.get("mask_png_base64")
        child_name = child_name or payload.get("child_name")
    if not image_filename or not aoi_id or not mask_png_base64:
        raise HTTPException(status_code=400, detail="image_filename, aoi_id, and mask_png_base64 are required")

    try:
        # Accept data URL or raw base64
        data_str = mask_png_base64
        if "," in data_str and data_str.lower().startswith("data:"):
            data_str = data_str.split(",", 1)[1]
        # Remove whitespace that can break base64 decoding
        data_str = data_str.replace("\n", "").replace("\r", "")
        raw = base64.b64decode(data_str)
        image_name = Path(image_filename).stem
        out_path = _aoi_mask_path(image_name, aoi_id, child_name)
        with open(out_path, 'wb') as f:
            f.write(raw)

        # Update defs with mask_path
        defs = _load_aoi_defs(image_filename, child_name)
        found = False
        for aoi in defs.get("aois", []):
            if aoi.get("aoi_id") == aoi_id or aoi.get("name") == aoi_id:
                aoi["mask_path"] = f"/gaze/{_safe_child_dir(child_name)}/{image_name}_{aoi_id}_mask.png"
                found = True
                break
        if not found:
            defs.setdefault("aois", []).append({
                "aoi_id": aoi_id,
                "name": aoi_id,
                "indices": [],
                "mask_path": f"/gaze/{_safe_child_dir(child_name)}/{image_name}_{aoi_id}_mask.png"
            })
        _save_aoi_defs(image_filename, defs, child_name)

        return {"success": True, "mask_url": f"/gaze/{_safe_child_dir(child_name)}/{image_name}_{aoi_id}_mask.png"}
    except Exception as e:
        print(f"AOI mask save error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save AOI mask")


@app.post("/aoi/fixation")
async def log_aoi_fixation(
    background_tasks: BackgroundTasks,
    image_filename: str = Form(...),
    object_index: int = Form(...),
    duration_ms: int = Form(0),
    start_ts: Optional[int] = Form(None),
    end_ts: Optional[int] = Form(None),
    phase: str = Form("end"),  # 'start' | 'progress' | 'end'
    audience: Optional[str] = Form("child"),
    mode: Optional[str] = Form("curiosity"),
    assistance: Optional[str] = Form(None),
    child_name: Optional[str] = Form(None)
):
    """Log a fixation on a specific AOI (object) for an image.

    - duration_ms is the fixation duration to accumulate.
    - Only objects with at least one fixation are stored in gaze/{child}/aoi/{image}_aois.json
    - Revisits increment when the last fixated object differs from the current one.
    """
    now_ts = int(time.time() * 1000)
    if start_ts is None and end_ts is None and duration_ms < 0:
        raise HTTPException(status_code=400, detail="Invalid fixation timing")

    image_name = Path(image_filename).stem
    # Normalize audience and mode; infer parent from assistance if audience missing
    raw_audience = (audience or "").lower()
    safe_mode = (mode or "curiosity").lower()
    raw_assistance = (assistance or "").lower()
    if not raw_audience:
        if raw_assistance.startswith("parent_"):
            safe_audience = "parent"
        else:
            safe_audience = "child"
    else:
        safe_audience = raw_audience
    # Map (audience, parentSupport) to assistance space; client can pass assistance explicitly
    # assistance: "child" | "parent_basic" | "parent_guided"
    safe_assistance = (raw_assistance or ("parent_guided" if safe_audience == "parent" and safe_mode == "mindwandering" else ("parent_basic" if safe_audience == "parent" else "child"))).lower()

    # Freeze gate: if this image is frozen, only allow 'end' phase to finalize fixations
    freeze_key = _freeze_key(image_name, child_name)
    is_frozen = _aoi_freeze.get(freeze_key)
    if is_frozen and phase != "end":
        return {
            "success": True,
            "frozen": True,
            "message": f"AOI {phase} updates are temporarily frozen while guidance is generated. Only end events allowed."
        }

    # Map index -> metadata from labels
    labels_json_path = Path("segmented_pictures/question") / f"{image_name}_labels.json"
    if not labels_json_path.exists():
        raise HTTPException(status_code=404, detail="Labels mapping not found")
    with open(labels_json_path, 'r') as f:
        labels = json.load(f)
    obj_meta = next((o for o in labels.get('objects', []) if o.get('index') == object_index), None)
    if obj_meta is None:
        raise HTTPException(status_code=404, detail="Object index not found in labels")
    # Ensure we have a stable object_id even if labels.json doesn't include it
    object_id_fallback = f"idx{obj_meta.get('index')}"
    obj_meta_object_id = obj_meta.get('object_id', object_id_fallback)

    # Load or create AOI file
    aoi_data = _load_aoi_file(image_name, image_filename, assistance=safe_assistance, child_name=child_name)

    # Find or create entry
    objects = aoi_data.get("objects", [])
    entry = None
    for o in objects:
        if o.get("index") == object_index:
            entry = o
            break
    if entry is None:
        entry = {
            "index": obj_meta["index"],
            "object_id": obj_meta_object_id,
            "bbox": obj_meta["bbox"],
            "center": obj_meta["center"],
            "area": obj_meta["area"],
            "fixation_count": 0,
            "fixation_duration": 0,
            "revisits": 0
        }
        objects.append(entry)
    else:
        # Backfill object_id if missing in existing entry
        if not entry.get("object_id"):
            entry["object_id"] = obj_meta_object_id

    # Determine timing
    if start_ts is None:
        if end_ts is None:
            end_ts = now_ts
        start_ts = max(0, int(end_ts) - int(duration_ms))
    if end_ts is None:
        end_ts = now_ts
    computed_duration = int(end_ts) - int(start_ts)
    if duration_ms and duration_ms > 0:
        computed_duration = int(duration_ms)

    # Update metrics on 'end' and allow incremental accumulation on 'progress'
    last_idx = _aoi_last_index.get(image_filename)
    just_saved_crop = False
    just_saved_url: Optional[str] = None
    if phase == "end":
        entry["fixation_count"] += 1
        entry["fixation_duration"] += max(0, int(computed_duration))
        if last_idx is not None and last_idx != object_index:
            entry["revisits"] += 1
        # Get current gaze coordinates for fixation record
        try:
            tobii_service = get_tobii_eye_tracking_service()
            current_gaze = tobii_service.get_current_gaze_position()
            gaze_x = current_gaze.get('x') if current_gaze else None
            gaze_y = current_gaze.get('y') if current_gaze else None
        except Exception:
            gaze_x = None
            gaze_y = None
            
        # Append finalized event row with coordinates
        _append_fixation_event(
            image_name=image_name,
            image_filename=image_filename,
            object_index=object_index,
            object_id=entry.get("object_id", obj_meta_object_id),
            start_ts=int(start_ts),
            end_ts=int(end_ts),
            duration_ms=int(computed_duration),
            assistance=safe_assistance,
            child_name=child_name,
            x_coordinate=gaze_x,
            y_coordinate=gaze_y
        )

        # Auto-save crop once when cumulative duration crosses threshold
        try:
            threshold_ms = 4000
            if int(entry.get("fixation_duration", 0)) >= threshold_ms and not entry.get("crop_saved"):
                url = _save_crop_for_index(image_filename, object_index, include_alpha=True)
                if url:
                    entry["crop_saved"] = True
                    entry["crop_url"] = url
                    entry["crop_saved_at"] = int(time.time() * 1000)
                    just_saved_crop = True
                    just_saved_url = url
        except Exception:
            pass
    elif phase == "progress":
        # Incrementally accumulate dwell without increasing fixation_count
        try:
            entry["fixation_duration"] += max(0, int(computed_duration))
        except Exception:
            pass
        # Run the same threshold check so long stares can trigger curiosity
        try:
            threshold_ms = 4000
            if int(entry.get("fixation_duration", 0)) >= threshold_ms and not entry.get("crop_saved"):
                url = _save_crop_for_index(image_filename, object_index, include_alpha=True)
                if url:
                    entry["crop_saved"] = True
                    entry["crop_url"] = url
                    entry["crop_saved_at"] = int(time.time() * 1000)
                    just_saved_crop = True
                    just_saved_url = url
        except Exception:
            pass

    # Track last index for revisit logic
    _aoi_last_index[image_filename] = object_index

    aoi_data["objects"] = objects
    _save_aoi_file(image_name, aoi_data, assistance=safe_assistance, child_name=child_name)

    # If a new crop was just saved, enqueue LLM guidance generation in background
    if just_saved_crop and just_saved_url:
        try:
            # STEP 1: Generate unique request ID and register request
            request_id = f"curiosity_{image_name}_{object_index}_{int(time.time() * 1000)}"
            register_guidance_request(image_filename, request_id, child_name)
            
            # Freeze gaze tracking updates for this image while generating guidance
            _aoi_freeze[_freeze_key(image_name, child_name)] = True

            def _generate_then_unfreeze():
                try:
                    # STEP 1: Check if request was cancelled before starting
                    if is_request_cancelled(request_id):
                        print(f"🚫 [STEP1] Skipping cancelled curiosity guidance {request_id}")
                        return
                    
                    generate_and_save_guidance(
                        image_filename,
                        int(object_index),
                        entry.get("object_id", obj_meta_object_id),
                        just_saved_url,
                        entry,
                        mode=safe_mode,
                        audience=safe_audience,
                        tracking_mode="eyetracking",
                        child_name=child_name
                    )
                finally:
                    # STEP 1: Clean up request regardless of success/failure
                    cleanup_guidance_request(request_id)
                    # Keep frozen until client explicitly unfreezes after assistant is dismissed

            background_tasks.add_task(_generate_then_unfreeze)
        except Exception:
            pass

    return {
        "success": True,
        "updated": entry,
        "file": f"/gaze/{_safe_child_dir(child_name)}/aoi/{image_name}_{safe_assistance}_aois.json",
        "events_file": f"/gaze/{_safe_child_dir(child_name)}/fixation/{image_name}_{safe_assistance}_fixations.json",
        "just_saved": just_saved_crop,
        "crop_url": just_saved_url
    }


@app.post("/aoi/freeze")
async def set_aoi_freeze(image_filename: str = Form(...), frozen: bool = Form(...), child_name: Optional[str] = Form(None)):
    try:
        image_name = Path(image_filename).stem
        key = _freeze_key(image_name, child_name)
        _aoi_freeze[key] = bool(frozen)
        # Freeze state set silently
        return {"success": True, "image": image_filename, "frozen": _aoi_freeze.get(key, False)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set freeze: {e}")


@app.get("/aoi/freeze/status")
async def get_aoi_freeze_status(image_filename: str, child_name: Optional[str] = None):
    image_name = Path(image_filename).stem
    return {"success": True, "image": image_filename, "frozen": bool(_aoi_freeze.get(_freeze_key(image_name, child_name), False))}


@app.post("/aoi/reset")
async def reset_aoi_and_crops(image_filename: str = Form(...), child_name: Optional[str] = Form(None)):
    try:
        image_name = Path(image_filename).stem
        # Clear freeze
        _aoi_freeze[_freeze_key(image_name, child_name)] = False

        # Delete AOI files in child-specific aoi and fixation folders
        child_dir = AOI_DIR / _safe_child_dir(child_name)
        aoi_subdir = child_dir / "aoi"
        fixation_subdir = child_dir / "fixation"
        
        # Find and delete all AOI files for this image (all assistance types)
        if aoi_subdir.exists():
            for aoi_file in aoi_subdir.glob(f"{image_name}_*_aois.json"):
                try:
                    aoi_file.unlink()
                except Exception:
                    pass
        
        # Find and delete all fixation files for this image (all assistance types)
        if fixation_subdir.exists():
            for fix_file in fixation_subdir.glob(f"{image_name}_*_fixations.json"):
                try:
                    fix_file.unlink()
                except Exception:
                    pass

        # Delete crops for this image
        try:
            for p in (STATIC_DIR / "crops").glob(f"{image_name}_*.png"):
                try:
                    p.unlink()
                except Exception:
                    pass
        except Exception:
            pass

        # Optionally clear recent state for this image
        _aoi_last_index.pop(image_filename, None)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")


@app.post("/aoi/reset-all")
async def reset_all_aoi_data():
    """Clear all gaze data and in-memory caches for a fresh session.

    Deletes only *_aois.json and *_fixations.json to preserve gaze area defs and masks.
    Also clears in-memory caches and unfreezes any images.
    """
    try:
        # Delete gaze files (aoi and fixation subfolders)
        removed = 0
        for child_dir in AOI_DIR.iterdir():
            if child_dir.is_dir():
                # Delete from aoi subfolder
                aoi_subdir = child_dir / "aoi"
                if aoi_subdir.exists():
                    for p in aoi_subdir.glob("*_aois.json"):
                        try:
                            p.unlink()
                            removed += 1
                        except Exception:
                            pass
                
                # Delete from fixation subfolder
                fixation_subdir = child_dir / "fixation"
                if fixation_subdir.exists():
                    for p in fixation_subdir.glob("*_fixations.json"):
                        try:
                            p.unlink()
                            removed += 1
                        except Exception:
                            pass

        # Clear in-memory caches/state
        _segmentation_cache.clear()
        _image_cache.clear()
        _recent_crops.clear()
        _aoi_last_index.clear()
        _label_map_cache.clear()
        _label_mapping_cache.clear()
        _aoi_freeze.clear()
        
        # STEP 1: Clear guidance request tracking
        _active_guidance_requests.clear()
        _guidance_cancellation_flags.clear()

        return {"success": True, "removed": removed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset-all failed: {e}")


@app.post("/llm/guidance")
async def generate_llm_guidance(
    image_filename: str = Form(...),
    audience: Optional[str] = Form("child"),
    mode: Optional[str] = Form("mindwandering"),
    used_objects: Optional[str] = Form("[]"),
    child_name: Optional[str] = Form(None)
):
    print(f"🚨 DEBUG: /llm/guidance ENTRY - image: {image_filename}, child: '{child_name}'")
    print(f"🚨 DEBUG: audience: '{audience}', mode: '{mode}'")
    """Generate LLM guidance for LLM-only mode using random object selection.

    Returns: { success, guidance_path, object_id, index? }
    """
    try:
        image_name = Path(image_filename).stem
        safe_audience = str(audience or "child").lower()
        # Accept legacy values but prefer canonical mindwandering here
        m = str(mode or "mindwandering").lower()
        # Accept legacy but prefer canonical
        if m in ("nudge", "mind-wandering", "mind_wandering"):
            safe_mode = "mindwandering"
        else:
            safe_mode = m
        
        # Parse used objects to avoid repetition
        try:
            used_objects_list = json.loads(used_objects) if used_objects else []
        except:
            used_objects_list = []

        # Load segmentation data
        labels_path = Path("segmented_pictures/question") / f"{image_name}_labels.json"
        if not labels_path.exists():
            raise HTTPException(status_code=404, detail=f"No segmentation data for {image_filename}")

        with open(labels_path, 'r') as f:
            labels_data = json.load(f)
        
        objects = labels_data.get("objects", [])
        if not objects:
            raise HTTPException(status_code=404, detail=f"No objects found in segmentation data for {image_filename}")

        # Filter out used objects and invalid objects
        available_objects = [
            obj for obj in objects 
            if (obj.get("index", 0) > 0 and 
                obj.get("object_id", f"idx{obj.get('index', 0)}") not in used_objects_list)
        ]
        
        if not available_objects:
            # If all objects have been used, reset and use any valid object
            available_objects = [obj for obj in objects if obj.get("index", 0) > 0]
            if not available_objects:
                raise HTTPException(status_code=404, detail="No valid objects available")

        # Randomly select an object
        import random
        selected_object = random.choice(available_objects)
        object_index = selected_object.get("index")
        object_id = selected_object.get("object_id", f"idx{object_index}")

        # STEP 1: Generate unique request ID and register request (cancel any existing)
        request_id = f"llm_{image_name}_{object_index}_{int(time.time() * 1000)}"
        register_guidance_request(image_filename, request_id, child_name)
        
        # Generate crop for selected object
        crop_url = _save_crop_for_index(image_filename, object_index, include_alpha=True)
        if not crop_url:
            # STEP 1: Clean up request on error
            cleanup_guidance_request(request_id)
            raise HTTPException(status_code=500, detail="Failed to create crop for selected object")

        # STEP 1: Check if request was cancelled before generating guidance
        if is_request_cancelled(request_id):
            print(f"🚫 [STEP1] Skipping cancelled LLM guidance {request_id}")
            cleanup_guidance_request(request_id)
            raise HTTPException(status_code=409, detail="Guidance request was cancelled")

        # Generate guidance with proper crop + context
        try:
            guidance_path = generate_and_save_guidance(
                image_filename,
                object_index,
                object_id,
                crop_url,
                selected_object,
                mode=safe_mode,
                audience=safe_audience,
                tracking_mode="llmonly",
                child_name=child_name
            )
        finally:
            # STEP 1: Clean up request after generation (success or failure)
            cleanup_guidance_request(request_id)

        if not guidance_path:
            print(f"LLM guidance generation failed for {image_filename}, object {object_id}")
            raise HTTPException(status_code=500, detail="Failed to generate LLM guidance content")

        return {
            "success": True,
            "guidance_path": guidance_path,
            "object_id": object_id,
            "index": object_index
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"LLM guidance error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate LLM guidance")


@app.post("/aoi/mindwandering")
async def mindwandering_child_attention(
    image_filename: str = Form(...),
    audience: Optional[str] = Form("child"),
    mode: Optional[str] = Form("mindwandering"),
    assistance: Optional[str] = Form(None),
    child_name: Optional[str] = Form(None)
):
    print(f"🚨 DEBUG: /aoi/mindwandering ENTRY - image: {image_filename}, child: '{child_name}', assistance: '{assistance}'")
    print(f"🚨 DEBUG: audience: '{audience}', mode: '{mode}'")
    """Pick an unexplored (or least explored) AOI and generate guidance to re-engage.

    Returns: { success, url, object_id, index, guidance_path? }
    """
    try:
        image_name = Path(image_filename).stem
        safe_audience = str(audience or "child").lower()
        safe_mode = str(mode or "mindwandering").lower()
        if safe_mode in ("nudge", "mind-wandering", "mind_wandering"):
            safe_mode = "mindwandering"
        safe_assistance = (assistance or ("parent_guided" if safe_audience == "parent" else "child")).lower()
        
        # STEP 1: Generate unique request ID and register request (cancel any existing)
        request_id = f"mindwandering_{image_name}_{int(time.time() * 1000)}"
        register_guidance_request(image_filename, request_id, child_name)
        
        # Freeze gaze tracking updates while nudging
        _aoi_freeze[ _freeze_key(image_name, child_name) ] = True

        # Load AOI data or build baseline
        aoi_data = _load_aoi_file(image_name, image_filename, assistance=safe_assistance, child_name=child_name)
        objects = aoi_data.get("objects", [])
        if not objects:
            # STEP 1: Clean up request on error
            cleanup_guidance_request(request_id)
            raise HTTPException(status_code=404, detail="No gaze objects available for nudging")

        # Prefer objects with zero fixation_count, else pick min fixation_duration
        zero_fix = [o for o in objects if int(o.get("fixation_count", 0)) == 0]
        if zero_fix:
            candidates = zero_fix
        else:
            # exclude background-like or invalid indices
            valid = [o for o in objects if int(o.get("index", 0)) > 0]
            if not valid:
                valid = objects
            candidates = sorted(valid, key=lambda o: int(o.get("fixation_duration", 0)))

        target = candidates[0]
        idx = int(target.get("index"))
        obj_id = target.get("object_id", f"idx{idx}")

        # Ensure we have a crop for this index
        url = _save_crop_for_index(image_filename, idx, include_alpha=True)
        if not url:
            # STEP 1: Clean up request on error
            cleanup_guidance_request(request_id)
            raise HTTPException(status_code=500, detail="Failed to create gaze crop for mindwandering")

        # STEP 1: Check if request was cancelled before generating guidance
        if is_request_cancelled(request_id):
            print(f"🚫 [STEP1] Skipping cancelled mindwandering guidance {request_id}")
            cleanup_guidance_request(request_id)
            raise HTTPException(status_code=409, detail="Guidance request was cancelled")

        # Generate guidance synchronously
        try:
            guidance_path = generate_and_save_guidance(
                image_filename,
                idx,
                obj_id,
                url,
                target,
                mode=safe_mode,
                audience=safe_audience,
                tracking_mode="eyetracking",
                child_name=child_name
            )
        finally:
            # STEP 1: Clean up request after generation (success or failure)
            cleanup_guidance_request(request_id)

        return {
            "success": True,
            "url": url,
            "object_id": obj_id,
            "index": idx,
            "guidance_path": guidance_path
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Mindwandering error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate mindwandering guidance")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "GazeStory Lab API is running!", "version": "1.0.0"}


@app.post("/generate")
async def generate_narration(
    image: UploadFile = File(...),
    language: str = Form("en-US")
):
    """
    Generate voice narration from a picture book image
    
    - **image**: Picture book page image (jpg, png)
    - **age**: Child's age (3-10)
    - **language**: Language code (en-US, es-ES, fr-FR)
    """
    
    try:
        # Validate file type
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Read and validate image
        image_data = await image.read()
        if len(image_data) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=400, detail="Image too large (max 10MB)")
        
        # Validate image format
        try:
            img = Image.open(io.BytesIO(image_data))
            img.verify()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid image format")
        
        # Step 1: Analyze image with VLM
        # Fixed target age range (4-6). Use age 5 as default complexity.
        narration_data = await NarrationService.analyze_image(
            image_data, 5, language
        )
        
        # Step 2: Apply safety filters
        safe_narration = SafetyFilter.filter_content(
            narration_data["narration_text"], 
            max_words=50 + (5 * 10)
        )
        
        # Step 3: Generate speech
        audio_url = await TTSService.synthesize_speech(safe_narration, language)
        
        # Step 4: Return response
        response = {
            "narration_text": safe_narration,
            "audio_url": audio_url,
            "language": language,
            "timestamp": int(time.time())
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/generate-from-filename")
async def generate_narration_from_filename(
    image_filenames: str = Form(...),  # comma-separated filenames
    language: str = Form("en-US")
):
    """
    Generate voice narration from picture book images using filenames
    
    - **image_filenames**: Picture book image filenames, comma-separated (e.g., "1.png,2.png,3.png")
    - **age**: Child's age (3-10)
    - **language**: Language code (en-US, es-ES, fr-FR)
    """
    
    try:
        # Parse image filenames
        filenames = [f.strip() for f in image_filenames.split(',') if f.strip()]
        if not filenames:
            raise HTTPException(status_code=400, detail="No image filenames provided")
        
        # Limit to maximum 4 images per request
        if len(filenames) > 4:
            filenames = filenames[:4]
        
        image_data_list = []
        valid_filenames = []
        
        # Read and validate all images
        for filename in filenames:
            image_path = Path("../pictures/question") / filename
            
            if not image_path.exists():
                print(f"Warning: Image file '{filename}' not found, skipping")
                continue
            
            try:
                with open(image_path, 'rb') as f:
                    image_data = f.read()
                
                # Validate image format
                img = Image.open(io.BytesIO(image_data))
                img.verify()
                
                image_data_list.append(image_data)
                valid_filenames.append(filename)
            except Exception as e:
                print(f"Warning: Invalid image format for '{filename}': {e}, skipping")
                continue
        
        if not image_data_list:
            raise HTTPException(status_code=400, detail="No valid images found")
        
        # Step 1: Analyze images with VLM
        if len(image_data_list) == 1:
            # Single image analysis
            narration_data = await NarrationService.analyze_image(
                image_data_list[0], 5, language
            )
        else:
            # Multiple images analysis
            narration_data = await NarrationService.analyze_multiple_images(
                image_data_list, valid_filenames, 5, language
            )
        
        # Step 2: Apply safety filters with longer content for multiple images
        word_limit = 50 + (5 * 10) + (len(image_data_list) * 30)
        safe_narration = SafetyFilter.filter_content(
            narration_data["narration_text"], 
            max_words=word_limit
        )
        
        # Step 3: Generate speech
        audio_url = await TTSService.synthesize_speech(safe_narration, language)
        
        # Step 4: Return response
        response = {
            "narration_text": safe_narration,
            "audio_url": audio_url,
            "language": language,
            "image_filenames": valid_filenames,
            "image_count": len(valid_filenames),
            "timestamp": int(time.time())
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/audio/{filename}")
async def get_audio(filename: str):
    """Serve audio files"""
    file_path = STATIC_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    return FileResponse(
        file_path,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=3600"}
    )


# Eye Tracking Endpoints
@app.get("/eye-tracking/status")
async def get_eye_tracking_status():
    """Get current status of the eye tracking system"""
    try:
        tobii_service = get_tobii_eye_tracking_service()
        status = tobii_service.get_status()
        return {
            "success": True,
            "status": status
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status": {
                "connected": False,
                "tracking": False,
                "eyetracker_model": None,
                "device_name": None
            }
        }

@app.post("/eye-tracking/connect")
async def connect_eye_tracker():
    """Connect to Tobii Pro Fusion eye tracker"""
    try:
        tobii_service = get_tobii_eye_tracking_service()
        success = tobii_service.find_and_connect_eyetracker()
        
        if success:
            return {
                "success": True,
                "message": "Eye tracker connected successfully",
                "status": tobii_service.get_status()
            }
        else:
            return {
                "success": False,
                "message": "Failed to connect to eye tracker",
                "status": tobii_service.get_status()
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error connecting to eye tracker: {str(e)}"
        }

@app.post("/eye-tracking/start")
async def start_eye_tracking():
    """Start real-time gaze data collection"""
    try:
        tobii_service = get_tobii_eye_tracking_service()
        
        if not tobii_service.is_connected:
            # Try to connect first
            if not tobii_service.find_and_connect_eyetracker():
                return {
                    "success": False,
                    "message": "Eye tracker not connected. Please connect first."
                }
        
        success = tobii_service.start_tracking()
        
        if success:
            return {
                "success": True,
                "message": "Eye tracking started successfully",
                "status": tobii_service.get_status()
            }
        else:
            return {
                "success": False,
                "message": "Failed to start eye tracking",
                "status": tobii_service.get_status()
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error starting eye tracking: {str(e)}"
        }

@app.post("/eye-tracking/stop")
async def stop_eye_tracking():
    """Stop gaze data collection"""
    try:
        tobii_service = get_tobii_eye_tracking_service()
        tobii_service.ensure_stopped()  # Force complete stop
        success = True
        
        return {
            "success": success,
            "message": "Eye tracking stopped" if success else "Failed to stop eye tracking",
            "status": tobii_service.get_status()
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error stopping eye tracking: {str(e)}"
        }

@app.post("/eye-tracking/set-image")
async def set_current_image(image_filename: str = Form(...)):
    """Set the current image being viewed for context"""
    try:
        tobii_service = get_tobii_eye_tracking_service()
        image_path = f"../pictures/question/{image_filename}"
        tobii_service.set_image_context(image_path)
        
        return {
            "success": True,
            "message": f"Current image set to {image_filename}",
            "image_path": image_path
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error setting current image: {str(e)}"
        }

@app.get("/eye-tracking/gaze-data")
async def get_current_gaze_data(count: int = 1):
    """Get the latest gaze data points"""
    try:
        tobii_service = get_tobii_eye_tracking_service()
        
        if not tobii_service.is_tracking:
            return {
                "success": False,
                "message": "Eye tracking not active",
                "gaze_data": []
            }
        
        gaze_data = tobii_service.get_latest_gaze_data(count)
        current_position = tobii_service.get_current_gaze_position()
        
        return {
            "success": True,
            "gaze_data": gaze_data,
            "current_position": current_position,
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error getting gaze data: {str(e)}",
            "gaze_data": []
        }

@app.post("/eye-tracking/disconnect")
async def disconnect_eye_tracker():
    """Disconnect from eye tracker"""
    try:
        tobii_service = get_tobii_eye_tracking_service()
        tobii_service.disconnect()
        
        return {
            "success": True,
            "message": "Eye tracker disconnected successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error disconnecting eye tracker: {str(e)}"
        }

@app.delete("/cleanup")
async def cleanup_temp_files():
    """Clean up old temporary files (call periodically)"""
    try:
        current_time = time.time()
        deleted_count = 0
        
        # Delete files older than 1 hour
        for file_path in STATIC_DIR.glob("*.wav"):
            if current_time - file_path.stat().st_mtime > 3600:
                file_path.unlink()
                deleted_count += 1
        
        return {"message": f"Cleaned up {deleted_count} files"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {e}")


if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8001, 
        reload=True
    )
