"""Mock Interview Agent — stateful multi-turn interview simulator.
Asks a question, listens to the student's approach, probes with follow-ups,
then gives structured feedback. Session state stored in Redis.

Round types (replaces plain DSA-topic-only rounds):
- technical_l1/l2/l3 — DSA questions, still tagged by TOPICS for weakness tracking
- behavioral / hr     — non-DSA, generic prompts, no topic tag needed

Also supports:
- company-grounded questions (via pyq_scraper_agent) when a company name is given
- adaptive topic/difficulty suggestion based on the student's weakness scorecard
"""
import json
import logging
import re
import uuid
from groq import AsyncGroq
from app.core.config import settings
from app.core.redis import redis_get, redis_set
from app.core.database import AsyncSessionLocal
from app.models.topic_attempt import TopicAttempt
from sqlalchemy import text

logger = logging.getLogger(__name__)

SESSION_TTL = 3600  # 1 hour

MODEL = "openai/gpt-oss-120b"

TOPICS = {
    "arrays": "array manipulation, two pointers, sliding window",
    "strings": "string processing, pattern matching",
    "trees": "binary trees, BST, traversals",
    "graphs": "BFS, DFS, graph algorithms",
    "dp": "dynamic programming",
    "linked_list": "linked list operations",
}

ROUND_TYPES = {
    "technical_l1": {"label": "Technical L1", "kind": "technical", "default_difficulty": "easy"},
    "technical_l2": {"label": "Technical L2", "kind": "technical", "default_difficulty": "medium"},
    "technical_l3": {"label": "Technical L3", "kind": "technical", "default_difficulty": "hard"},
    "behavioral": {"label": "Behavioral", "kind": "behavioral", "default_difficulty": "medium"},
    "hr": {"label": "HR / Screening", "kind": "hr", "default_difficulty": "medium"},
}

QUESTION_PROMPT = """You are conducting a technical coding interview for a student practicing for placements.

Round: {round_label}
Topic: {topic} ({topic_desc})
Difficulty: {difficulty}

Ask ONE clear, well-known-style DSA interview question on this topic, appropriate for the difficulty level.
Keep it concise — like a real interviewer would state it, 2-4 sentences.

Return ONLY JSON: {{"question": "the question text"}}"""

BEHAVIORAL_PROMPT = """You are conducting a BEHAVIORAL interview round for a student practicing for placements.

Ask ONE well-known-style behavioral interview question (e.g. about teamwork, conflict,
failure, leadership, handling pressure) — the kind real interviewers ask in this round.
Keep it concise, 1-3 sentences, like a real interviewer speaking.

Return ONLY JSON: {{"question": "the question text"}}"""

HR_PROMPT = """You are conducting an HR / screening interview round for a student practicing for placements.

Ask ONE well-known-style HR screening question (e.g. about career goals, why this
company, salary expectations framing, availability, strengths/weaknesses) — the kind
real HR interviewers ask early in the process.
Keep it concise, 1-3 sentences, like a real interviewer speaking.

Return ONLY JSON: {{"question": "the question text"}}"""

FOLLOWUP_PROMPT = """You are an interviewer conducting a {round_kind} round. Conversation so far:

Question asked: {question}

Student's response so far:
{transcript}

Latest student message: {latest_message}

As the interviewer, respond naturally to what they said:
- If their answer is vague, ask them to clarify or give a specific example
- If they gave a solid answer, probe deeper — ask a natural follow-up an interviewer would ask
- If they seem stuck, give a small nudge (not the answer)
- Keep responses SHORT (1-3 sentences) like a real interviewer speaking, not an essay
- After 4-5 exchanges, if they've covered the question well, wrap up and say you'll give feedback now

Return ONLY JSON: {{"interviewer_response": "...", "should_end": false}}"""

FEEDBACK_PROMPT = """You are an interviewer giving final feedback after this {round_kind} interview round.

Question: {question}
Full transcript:
{transcript}

Give structured, honest, encouraging feedback — like a real interviewer debrief.

Return ONLY JSON:
{{
  "strengths": ["what they did well"],
  "improvements": ["specific things to work on"],
  "complexity_understanding": "assessment of technical/complexity understanding, or 'N/A' for non-technical rounds",
  "communication": "assessment of how clearly they explained their thinking",
  "overall_rating": "Strong Hire / Hire / Borderline / Needs Practice",
  "summary": "2-3 sentence overall summary"
}}"""


def _clean_raw(raw: str) -> str:
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"```json\s*|\s*```", "", raw)
    return raw.strip()


def _is_junk(text_val: str) -> bool:
    if not text_val:
        return True
    stripped = text_val.strip().strip(".").strip()
    return len(stripped) < 3


async def _call_groq(prompt: str, temperature: float, max_tokens: int) -> str:
    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    response = await client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    raw = response.choices[0].message.content or ""
    cleaned = _clean_raw(raw)
    if not cleaned:
        logger.warning(f"Groq returned empty/unparseable content. Raw: {raw!r}")
    return cleaned


async def suggest_adaptive_pick(user_id: str) -> dict:
    """Look at this user's TopicAttempt history and suggest a topic + difficulty
    to practice next. Only meaningful for technical rounds (behavioral/HR aren't
    topic-tagged). Falls back to a safe default if there's no history yet."""
    default = {"topic": "arrays", "difficulty": "medium", "reason": "Getting started — arrays is a solid first pick."}
    if not user_id:
        return default
    try:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                text("""
                    SELECT topic,
                           COUNT(*) AS attempts,
                           AVG(CASE WHEN is_correct THEN 1.0 ELSE 0.0 END) AS success_rate
                    FROM topic_attempts
                    WHERE user_id = :uid AND is_correct IS NOT NULL AND topic != 'general'
                    GROUP BY topic
                    ORDER BY success_rate ASC, attempts DESC
                """),
                {"uid": user_id},
            )).fetchall()
        if not rows:
            return default
        weakest = rows[0]
        difficulty = "easy" if weakest.success_rate < 0.4 else "medium"
        return {
            "topic": weakest.topic,
            "difficulty": difficulty,
            "reason": f"You're at {round(weakest.success_rate * 100)}% success in {weakest.topic} — worth another round.",
        }
    except Exception as e:
        logger.warning(f"Adaptive suggestion failed (non-fatal, using default): {e}")
        return default


async def start_interview(
    topic: str = None,
    difficulty: str = "medium",
    user_id: str = None,
    company: str = None,
    round_type: str = "technical_l1",
) -> dict:
    session_id = str(uuid.uuid4())
    round_info = ROUND_TYPES.get(round_type, ROUND_TYPES["technical_l1"])
    round_kind = round_info["kind"]
    question = None
    grounded = False

    if round_kind == "technical" and company:
        from app.agents.pyq_scraper_agent import generate_company_question
        try:
            result = await generate_company_question(company, topic=topic, difficulty=difficulty)
            question = result.get("question")
            topic = result.get("topic", topic or "arrays")
            grounded = result.get("grounded", False)
        except Exception as e:
            logger.error(f"Company-grounded question generation failed: {e}")

    if round_kind == "technical":
        if not topic:
            topic = "arrays"
        topic_desc = TOPICS.get(topic, topic)
        if not question:
            try:
                cleaned = await _call_groq(
                    QUESTION_PROMPT.format(round_label=round_info["label"], topic=topic, topic_desc=topic_desc, difficulty=difficulty),
                    temperature=0.7, max_tokens=400,
                )
                match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                if match:
                    candidate = json.loads(match.group(0)).get("question", "")
                    if not _is_junk(candidate):
                        question = candidate.strip()
            except Exception as e:
                logger.error(f"Interview start error: {e}")
        if not question:
            question = f"Tell me how you'd approach a common {topic} problem — walk me through your thinking."
    else:
        # Behavioral / HR — no DSA topic involved
        topic = round_kind  # tag TopicAttempt with 'behavioral'/'hr' instead of a DSA topic
        prompt = BEHAVIORAL_PROMPT if round_kind == "behavioral" else HR_PROMPT
        try:
            cleaned = await _call_groq(prompt, temperature=0.7, max_tokens=300)
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                candidate = json.loads(match.group(0)).get("question", "")
                if not _is_junk(candidate):
                    question = candidate.strip()
        except Exception as e:
            logger.error(f"{round_kind} interview start error: {e}")
        if not question:
            question = ("Tell me about a time you faced a conflict on a team and how you handled it."
                        if round_kind == "behavioral"
                        else "Walk me through why you're interested in this role.")

    session = {
        "session_id": session_id,
        "user_id": user_id,
        "topic": topic,
        "round_type": round_type,
        "round_kind": round_kind,
        "difficulty": difficulty,
        "company": company,
        "grounded": grounded,
        "question": question,
        "transcript": [],
        "ended": False,
    }
    await redis_set(f"interview:{session_id}", session, ttl=SESSION_TTL)
    return {"session_id": session_id, "question": question, "topic": topic, "round_type": round_type, "grounded": grounded}


async def continue_interview(session_id: str, message: str) -> dict:
    session = await redis_get(f"interview:{session_id}")
    if not session:
        return {"error": "Session expired or not found"}
    if isinstance(session, str):
        session = json.loads(session)

    round_kind = session.get("round_kind", "technical")
    session["transcript"].append({"role": "student", "text": message})
    transcript_str = "\n".join(f"{t['role']}: {t['text']}" for t in session["transcript"])

    interviewer_response = None
    should_end = False
    try:
        cleaned = await _call_groq(
            FOLLOWUP_PROMPT.format(round_kind=round_kind, question=session["question"], transcript=transcript_str, latest_message=message),
            temperature=0.6, max_tokens=500,
        )
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            candidate = parsed.get("interviewer_response", "")
            if not _is_junk(candidate):
                interviewer_response = candidate.strip()
                should_end = bool(parsed.get("should_end", False))
    except Exception as e:
        logger.error(f"Interview continue error: {e}")

    if not interviewer_response:
        interviewer_response = "Could you walk me through that a bit more?"

    session["transcript"].append({"role": "interviewer", "text": interviewer_response})
    session["ended"] = should_end
    await redis_set(f"interview:{session_id}", session, ttl=SESSION_TTL)

    return {
        "interviewer_response": interviewer_response,
        "should_end": should_end,
        "session_id": session_id,
    }


async def get_interview_feedback(session_id: str) -> dict:
    session = await redis_get(f"interview:{session_id}")
    if not session:
        return {"error": "Session expired or not found"}
    if isinstance(session, str):
        session = json.loads(session)

    round_kind = session.get("round_kind", "technical")
    transcript_str = "\n".join(f"{t['role']}: {t['text']}" for t in session["transcript"])

    parsed = None
    try:
        cleaned = await _call_groq(
            FEEDBACK_PROMPT.format(round_kind=round_kind, question=session["question"], transcript=transcript_str),
            temperature=0.3, max_tokens=800,
        )
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            candidate = json.loads(match.group(0))
            if candidate.get("summary") and not _is_junk(candidate["summary"]):
                parsed = candidate
    except Exception as e:
        logger.error(f"Interview feedback error: {e}")

    if parsed is None:
        parsed = {
            "strengths": [], "improvements": [], "complexity_understanding": "N/A",
            "communication": "N/A", "overall_rating": "N/A",
            "summary": "Could not generate feedback.",
        }

    # Log topic attempt for adaptive scorecard — best-effort, never blocks feedback delivery
    try:
        rating = parsed.get("overall_rating", "")
        is_correct = rating in ("Strong Hire", "Hire")
        async with AsyncSessionLocal() as log_db:
            log_db.add(TopicAttempt(
                user_id=session.get("user_id"),
                topic=session["topic"],
                source="interview" if not session.get("company") else "pyq",
                company=session.get("company"),
                is_correct=is_correct,
                difficulty=session.get("difficulty", "medium"),
            ))
            await log_db.commit()
    except Exception as e:
        logger.error(f"TopicAttempt log failed (non-fatal): {e}")

    return parsed