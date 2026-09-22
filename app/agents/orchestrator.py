"""Master Orchestrator Agent — classifies incoming student intent and routes
to the correct specialist agent. This is the single entry point for all
agentic features in CodeZen, implemented as a lightweight LangGraph-style router.
"""
import json
import logging
import re
from enum import Enum
from groq import AsyncGroq
from app.core.config import settings

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    TUTOR = "tutor"                 # general Q&A / debugging help — Socratic, hints only
    CODE_EXAMPLE = "code_example"   # explicit "give me code for X" — full working code, not Socratic
    CODE_REVIEW = "code_review"     # review my code
    TEST_CASES = "test_cases"       # generate test cases
    INTERVIEW = "interview"         # mock interview
    COMPANY_PREP = "company_prep"   # "prep me for <company>" — company-grounded PYQ practice
    PROGRESS = "progress"           # how am I doing
    UNKNOWN = "unknown"


CLASSIFY_PROMPT = """Classify this student message into exactly ONE intent category.

Message: "{message}"
Has code attached: {has_code}

Categories:
- tutor: general programming question, "explain X", "why is my code failing", asking for a hint or concept explanation — student wants to think it through, not be given the answer
- code_example: explicitly asking to BE GIVEN working code/implementation — "give me code for X", "show me the implementation", "write code that does Y", "code for <algorithm> algo"
- code_review: explicitly asking to review/critique code quality, find bugs, or improve their own code
- test_cases: asking for test cases, edge cases, or "will this handle X input"
- interview: asking to practice a mock interview, or practice DSA questions interview-style, with no company named
- company_prep: asking to prepare for a SPECIFIC named company's interview (e.g. "prep me for Cognizant", "TCS interview questions")
- progress: asking about their stats, progress, weak areas, how they're doing overall

Return ONLY JSON: {{"intent": "one of the categories above", "confidence": 0.9}}"""


async def classify_intent(message: str, has_code: bool = False) -> Intent:
    """Fast intent classification using a small/cheap model call."""
    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model="qwen/qwen3.6-27b",  # fast model for routing decisions
            messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(
                message=message, has_code=has_code)}],
            temperature=0.0,
            max_tokens=60,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            intent_str = parsed.get("intent", "tutor")
            try:
                return Intent(intent_str)
            except ValueError:
                return Intent.TUTOR
    except Exception as e:
        logger.error(f"Intent classification error: {e}")

    return Intent.TUTOR  # safe default — tutor agent handles general queries


def _extract_company_name(message: str) -> str:
    """Cheap heuristic: strip common filler words, keep capitalized tokens."""
    stopwords = {"prep", "me", "for", "interview", "questions", "the", "a", "an", "please", "help", "with"}
    words = re.findall(r"[A-Za-z][A-Za-z&.]*", message)
    candidates = [w for w in words if w.lower() not in stopwords]
    return " ".join(candidates[:3]) if candidates else ""


async def route_and_handle(
    message: str,
    code: str = None,
    language: str = "python",
    room_id: str = None,
    user_id: str = None,
    db=None,
    forced_intent: str = None,
) -> dict:
    """
    Master routing function. Classifies the message (unless forced_intent is
    supplied by the client, e.g. when a specific button was tapped) and
    dispatches to the correct specialist agent.
    """
    if forced_intent:
        try:
            intent = Intent(forced_intent)
        except ValueError:
            intent = await classify_intent(message, has_code=bool(code))
    else:
        intent = await classify_intent(message, has_code=bool(code))

    logger.info(f"Orchestrator routed to: {intent.value}")

    if intent == Intent.CODE_EXAMPLE:
        from app.agents.code_example_agent import generate_code_example
        result = await generate_code_example(message, language=language)
        return {"intent": intent.value, "data": result}

    elif intent == Intent.CODE_REVIEW:
        from app.agents.code_review_agent import review_code
        if not code:
            return {"intent": intent.value, "error": "No code provided to review"}
        result = await review_code(code, language, problem_description=message, user_id=user_id)
        return {"intent": intent.value, "data": result}

    elif intent == Intent.TEST_CASES:
        from app.agents.testcase_agent import generate_test_cases
        if not code:
            return {"intent": intent.value, "error": "No code provided to generate test cases for"}
        result = await generate_test_cases(code, language, problem_description=message)
        return {"intent": intent.value, "data": result}

    elif intent == Intent.PROGRESS:
        from app.agents.progress_agent import analyze_progress
        if db is None or user_id is None:
            return {"intent": intent.value, "error": "Progress requires an authenticated session"}
        result = await analyze_progress(db, user_id)
        return {"intent": intent.value, "data": result}

    elif intent == Intent.COMPANY_PREP:
        company_guess = _extract_company_name(message)
        return {"intent": intent.value, "data": {"redirect": "interview_flow", "company_guess": company_guess}}

    elif intent == Intent.INTERVIEW:
        return {"intent": intent.value, "data": {"redirect": "interview_flow"}}

    else:
        from app.agents.graph import run_agent
        result = await run_agent(
            query=message, code=code, language=language,
            room_id=room_id, user_id=user_id,
        )
        return {"intent": Intent.TUTOR.value, "data": result}