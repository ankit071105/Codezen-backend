import base64
import json
import logging
import os
import re
from groq import AsyncGroq
from app.core.config import settings

logger = logging.getLogger(__name__)

# Set tesseract path for Mac M1 homebrew
_TESSERACT_PATHS = [
    '/opt/homebrew/bin/tesseract',
    '/usr/local/bin/tesseract',
    '/usr/bin/tesseract',
]

def _setup_tesseract():
    try:
        import pytesseract
        # Try env var first
        env_path = os.environ.get('TESSERACT_CMD')
        if env_path and os.path.exists(env_path):
            pytesseract.pytesseract.tesseract_cmd = env_path
            return True
        # Try known paths
        for path in _TESSERACT_PATHS:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                logger.info(f"Tesseract found at: {path}")
                return True
        return False
    except ImportError:
        return False

_tesseract_available = _setup_tesseract()


async def extract_from_image(
    image_base64: str,
    language_hint: str = "python",
    media_type: str = "image/png",
) -> dict:
    """Use Groq compound (vision capable) to read handwritten code directly."""

    # Try vision first via a Groq multimodal model
    vision_result = await _vision_extract(image_base64, language_hint, media_type)
    if vision_result and vision_result.get("confidence", 0) >= 0.4 and vision_result.get("code", "").strip():
        return vision_result

    # Fallback: OCR + LLM cleanup
    logger.info("Vision failed, falling back to OCR")
    raw_text = _ocr_extract(image_base64)
    logger.info(f"OCR raw: {repr(raw_text[:200])}")
    if not raw_text.strip():
        return {
            "code": "", "language": language_hint,
            "confidence": 0.0,
            "notes": "Could not read. Write larger with clear block letters.",
            "source": "ocr_empty",
        }
    return await _llm_clean_code(raw_text, language_hint)


async def _vision_extract(image_base64: str, language_hint: str, media_type: str) -> dict:
    """Use a Groq multimodal model directly for vision."""
    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        # qwen3.6-27b supports vision via image_url in content array
        response = await client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_base64}"},
                    },
                    {
                        "type": "text",
                        "text": f"""Read the handwritten {language_hint} code in this image.
Pay attention to: + (plus), - (minus), * (multiply), / (divide), () brackets, numbers.
Return ONLY JSON: {{"code": "the exact code", "confidence": 0.9, "notes": "unclear parts"}}""",
                    },
                ],
            }],
            temperature=0.1,
            max_tokens=256,
        )
        raw = response.choices[0].message.content.strip()
        logger.info(f"Vision raw: {raw[:300]}")
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            code = result.get("code", "").replace("\\n", "\n")
            return {
                "code": code, "language": language_hint,
                "confidence": float(result.get("confidence", 0.8)),
                "notes": result.get("notes", ""),
                "source": "groq_vision",
            }
    except Exception as e:
        logger.error(f"Vision error: {e}")
    return None


def _ocr_extract(image_base64: str) -> str:
    try:
        import pytesseract
        from PIL import Image, ImageFilter, ImageEnhance, ImageOps
        import io

        # Fix base64 padding if needed
        missing = len(image_base64) % 4
        if missing:
            image_base64 += '=' * (4 - missing)
        img_bytes = base64.b64decode(image_base64, validate=False)
        logger.info(f"Canvas image bytes: {len(img_bytes)}")
        img = Image.open(io.BytesIO(img_bytes))
        img.save('/tmp/canvas_debug.png')
        logger.info(f"Canvas image size: {img.size} mode: {img.mode}")

        # Convert to grayscale
        img = img.convert("L")

        # Invert if dark background (white text on dark)
        avg = sum(img.getdata()) / len(img.getdata())
        if avg < 128:
            img = ImageOps.invert(img)

        # Enhance contrast
        img = ImageEnhance.Contrast(img).enhance(3.0)
        img = ImageEnhance.Sharpness(img).enhance(2.0)

        # Resize for better OCR (upscale small images)
        w, h = img.size
        if w < 600:
            img = img.resize((w * 2, h * 2), Image.LANCZOS)

        # Threshold — make it pure black and white
        img = img.point(lambda x: 0 if x < 140 else 255, '1').convert('L')

        config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(img, config=config)
        return text.strip()

    except Exception as e:
        logger.error(f"OCR error: {e}")
        return ""


async def _llm_clean_code(raw_text: str, language_hint: str) -> dict:
    """Use LLM to fix OCR errors and format as valid code."""
    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)

        prompt = f"""You are a handwriting-to-code converter. OCR scanned handwritten {language_hint} code and produced noisy text.

OCR output (noisy, may have character errors):
{raw_text}

Your job: identify what {language_hint} code was most likely written, based on:
1. The OCR text as the primary signal — trust the CHARACTER SHAPES
2. Common {language_hint} keywords: print, def, for, if, else, return, while, import, class
3. Do NOT invent new logic — only fix obvious OCR character mistakes
4. If OCR shows "Pr" followed by letters — it's likely "print"
5. If OCR shows numbers and operators like 2+3 — keep them as-is

CRITICAL: Do not change the meaning. If it looks like print(2+3), return print(2+3). Do not convert to def or class.

Return ONLY valid JSON:
{{"code": "corrected {language_hint} code", "confidence": 0.75, "notes": "what was corrected"}}"""

        response = await client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=512,
        )

        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            raw = json_match.group(0)

        result = json.loads(raw)
        code = result.get("code", "").replace("\\n", "\n")

        return {
            "code": code,
            "language": language_hint,
            "confidence": float(result.get("confidence", 0.7)),
            "notes": result.get("notes", ""),
            "source": "ocr+llm",
        }

    except Exception as e:
        logger.error(f"LLM cleanup error: {e}")
        # Return raw OCR if LLM fails
        return {
            "code": raw_text,
            "language": language_hint,
            "confidence": 0.4,
            "notes": "OCR only — LLM cleanup failed",
            "source": "ocr_only",
        }