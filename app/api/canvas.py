from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.dependencies import get_current_user
from app.models.user import User
from app.agents.canvas_agent import extract_from_image
from app.runner.sandbox import run_code, LANGUAGE_CONFIGS
from app.complexity.analyzer import analyze_complexity
from app.runner.debugger import debug_python

router = APIRouter(prefix="/canvas", tags=["canvas"])


class ImageExtractRequest(BaseModel):
    image_base64: str
    language_hint: str = "python"
    media_type: str = "image/jpeg"


class SvgExtractRequest(BaseModel):
    svg_content: str
    language_hint: str = "python"
    stroke_count: int = 0


class CanvasRunRequest(BaseModel):
    code: str
    language: str
    room_id: Optional[str] = None


@router.post("/extract")
async def extract_from_image_endpoint(
    payload: ImageExtractRequest,
    current_user: User = Depends(get_current_user),
):
    if not payload.image_base64:
        raise HTTPException(status_code=400, detail="image_base64 required")
    return await extract_from_image(
        image_base64=payload.image_base64,
        language_hint=payload.language_hint,
        media_type=payload.media_type,
    )


@router.post("/run")
async def run_canvas_code(
    payload: CanvasRunRequest,
    current_user: User = Depends(get_current_user),
):
    if payload.language.lower() not in LANGUAGE_CONFIGS:
        raise HTTPException(status_code=400, detail="Language not supported")
    result = await run_code(payload.language, payload.code)
    return {
        "stdout": result.stdout, "stderr": result.stderr,
        "exit_code": result.exit_code, "runtime_ms": result.runtime_ms,
        "timed_out": result.timed_out,
        "is_success": result.exit_code == 0 and not result.timed_out,
    }


@router.post("/analyze")
async def analyze_canvas_code(
    payload: CanvasRunRequest,
    current_user: User = Depends(get_current_user),
):
    c = analyze_complexity(payload.code, payload.language)
    return {
        "time_complexity": c.time_complexity, "space_complexity": c.space_complexity,
        "confidence": c.confidence, "explanation": c.explanation, "suggestions": c.suggestions,
    }


@router.post("/debug")
async def debug_canvas_code(
    payload: CanvasRunRequest,
    current_user: User = Depends(get_current_user),
):
    if payload.language.lower() != "python":
        raise HTTPException(status_code=400, detail="Debugger supports Python only")
    return await debug_python(payload.code)


class MlkitExtractRequest(BaseModel):
    raw_text: str
    language_hint: str = "python"
    all_candidates: list = []


@router.post("/extract-mlkit")
async def extract_from_mlkit(
    payload: MlkitExtractRequest,
    current_user: User = Depends(get_current_user),
):
    """Clean up ML Kit recognized text into valid code using LLM."""
    try:
        from groq import AsyncGroq
        from app.core.config import settings
        import re, json

        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        candidates_str = ", ".join(f'"{c}"' for c in payload.all_candidates[:5])

        prompt = f"""ML Kit handwriting recognition produced these candidates for handwritten {payload.language_hint} code:
Primary: "{payload.raw_text}"
Other candidates: {candidates_str}

Convert the best matching candidate to valid {payload.language_hint} code.
Fix only obvious character recognition errors (e.g. 'I' vs '1', 'O' vs '0').
Do NOT change the logic or add new code.

Return ONLY JSON: {{"code": "valid code here", "confidence": 0.9}}"""

        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=256,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            return {
                "code": result.get("code", payload.raw_text),
                "confidence": float(result.get("confidence", 0.8)),
                "source": "mlkit+llm",
            }
    except Exception as e:
        pass
    return {"code": payload.raw_text, "confidence": 0.7, "source": "mlkit"}


# ── Hybrid generator endpoint ─────────────────────────────────────────
class CanvasGenerateRequest(BaseModel):
    nodes: list[dict]
    connections: list[dict]
    language: str = "python"


@router.post("/generate")
async def generate_canvas_code(
    payload: CanvasGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Hybrid generator:
    - Pure rule engine when all labels are valid Python (no LLM call)
    - One batched LLM call only for dirty (pseudocode/natural language) labels
    Returns: { code, used_llm, llm_badge_nodes, dirty_count, error }
    """
    from app.agents.canvas_generator import generate
    result = await generate(
        nodes_raw=payload.nodes,
        connections_raw=payload.connections,
        language=payload.language,
    )
    return result