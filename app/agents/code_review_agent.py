"""Code Review Agent — analyzes student code for bugs, style, complexity issues.
Does NOT rewrite the code — gives structured educational feedback."""
import json
import logging
import re
from groq import AsyncGroq
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.topic_attempt import TopicAttempt
from app.agents.interview_agent import TOPICS

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """You are a senior code reviewer helping a student learn — not a code fixer.

Student's {language} code:
```
{code}
```

{problem_context}

Review this code like a mentor would. Identify:
1. BUGS — logic errors, edge cases missed (be specific about which input breaks it)
2. STYLE — naming, readability, structure issues
3. COMPLEXITY — is there a more efficient approach? (mention Big-O if relevant)
4. GOOD — what did they do well? (always include at least one positive)

Do NOT rewrite their code. Point at specific lines/logic and explain WHY it's an issue,
so the student understands the reasoning rather than just copying a fix.

Return ONLY this JSON:
{{
  "bugs": ["issue 1", "issue 2"],
  "style": ["issue 1"],
  "complexity": {{"current": "O(n^2)", "note": "explanation of a better approach if any, else null"}},
  "good": ["what they did well"],
  "overall_score": 7,
  "summary": "one sentence overall verdict"
}}"""


def _infer_topic(code: str, problem_description: str) -> str:
    """Cheap keyword-match topic inference — no extra LLM call.
    Reuses the same TOPICS dict interview_agent.py already defines, so
    weakness tracking uses one consistent topic taxonomy across features.
    Good enough for v1; swap for an LLM classify call later if noisy."""
    text = (code + " " + problem_description).lower()
    for topic, desc in TOPICS.items():
        keywords = [topic] + [w.strip() for w in desc.split(",")]
        if any(kw in text for kw in keywords):
            return topic
    return "general"


async def review_code(code: str, language: str, problem_description: str = "", user_id: str = None) -> dict:
    result = None
    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        problem_context = f"Problem they're solving: {problem_description}" if problem_description else ""

        response = await client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[{
                "role": "user",
                "content": REVIEW_PROMPT.format(language=language, code=code, problem_context=problem_context),
            }],
            temperature=0.2,
            max_tokens=1024,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
    except Exception as e:
        logger.error(f"Code review error: {e}")

    if result is None:
        result = {
            "bugs": [], "style": [], "complexity": {"current": "unknown", "note": None},
            "good": [], "overall_score": 0,
            "summary": "Could not analyze code — try again.",
        }

    # Log topic attempt for adaptive scorecard — best-effort, never blocks review delivery
    try:
        topic = _infer_topic(code, problem_description)
        async with AsyncSessionLocal() as log_db:
            log_db.add(TopicAttempt(
                user_id=user_id,
                topic=topic,
                source="code_review",
                score=result.get("overall_score"),
            ))
            await log_db.commit()
    except Exception as e:
        logger.error(f"TopicAttempt log failed (non-fatal): {e}")

    return result