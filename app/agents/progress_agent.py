"""Progress Analyzer Agent — looks at a student's submission history and
produces a weak/strong topic breakdown + recommendations.
Mostly DB analytics; LLM used only for the final natural-language summary.

Extended with:
- get_topic_breakdown(): weak/strong topics from TopicAttempt history
- get_diagnostic_report(): post-session style gap analysis, LLM-summarized
"""
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from collections import Counter
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from groq import AsyncGroq
from app.core.config import settings
from app.models.submission import Submission

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """A student has this coding practice history over the last 30 days:

Total submissions: {total}
Success rate: {success_rate}%
Languages used: {languages}
Most active days: {active_days}
Recent failure patterns (error snippets): {error_patterns}

Write a short, encouraging, actionable summary (3-4 sentences) for the student.
Mention what they're doing well and ONE specific, concrete thing to focus on next.
Speak directly to the student ("you"), be warm but honest.

Return ONLY JSON: {{"summary": "...", "recommended_focus": "one specific topic or skill"}}"""

DIAGNOSTIC_PROMPT = """A student's topic-wise performance (interviews, code reviews, company practice questions):

{topic_lines}

Write a short diagnostic report:
- 1-2 sentences on strong topics
- 1-2 sentences on weak topics
- ONE specific, concrete recommendation for what to revise before their next attempt

Speak directly to the student ("you"), be honest but encouraging.

Return ONLY JSON: {{"strong_summary": "...", "weak_summary": "...", "recommendation": "..."}}"""


async def analyze_progress(db: AsyncSession, user_id: str) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=30)

    result = await db.execute(
        select(Submission).where(
            Submission.user_id == user_id,
            Submission.created_at >= since,
        ).order_by(Submission.created_at.desc())
    )
    submissions = result.scalars().all()

    if not submissions:
        return {
            "total_submissions": 0,
            "success_rate": 0,
            "languages": {},
            "summary": "No recent activity. Start solving problems to see your progress here!",
            "recommended_focus": "Get started with a few basic problems",
        }

    total = len(submissions)
    successes = sum(1 for s in submissions if s.exit_code == 0 and not s.timed_out)
    success_rate = round((successes / total) * 100, 1)

    lang_counter = Counter(s.language for s in submissions)
    languages = dict(lang_counter.most_common())

    day_counter = Counter(s.created_at.strftime("%A") for s in submissions)
    active_days = [d for d, _ in day_counter.most_common(3)]

    error_snippets = [s.stderr[:150] for s in submissions if s.stderr][:5]

    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[{"role": "user", "content": SUMMARY_PROMPT.format(
                total=total, success_rate=success_rate, languages=languages,
                active_days=active_days, error_patterns=error_snippets or "none",
            )}],
            temperature=0.4,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        llm_result = json.loads(match.group(0)) if match else {}
    except Exception as e:
        logger.error(f"Progress summary error: {e}")
        llm_result = {}

    return {
        "total_submissions": total,
        "success_rate": success_rate,
        "languages": languages,
        "most_active_days": active_days,
        "summary": llm_result.get("summary", f"You've made {total} submissions with a {success_rate}% success rate."),
        "recommended_focus": llm_result.get("recommended_focus", "Keep practicing consistently"),
    }


async def get_topic_breakdown(db: AsyncSession, user_id: str) -> dict:
    """Weak/strong topic breakdown from TopicAttempt history (interviews,
    code reviews, PYQ practice). Read-only, computed on the fly — no
    separate scorecard table needed, TopicAttempt rows are the source of truth."""
    try:
        rows = (await db.execute(
            text("""
                SELECT topic,
                       COUNT(*) AS attempts,
                       AVG(CASE WHEN is_correct THEN 1.0 ELSE 0.0 END) AS success_rate,
                       AVG(score) AS avg_score
                FROM topic_attempts
                WHERE user_id = :uid
                GROUP BY topic
                ORDER BY success_rate ASC NULLS LAST
            """),
            {"uid": user_id},
        )).fetchall()
    except Exception as e:
        logger.error(f"Topic breakdown query failed: {e}")
        return {"weak": [], "strong": [], "topics": []}

    topics = [
        {
            "topic": r.topic,
            "attempts": r.attempts,
            "success_rate": round(float(r.success_rate) * 100, 1) if r.success_rate is not None else None,
            "avg_score": round(float(r.avg_score), 1) if r.avg_score is not None else None,
        }
        for r in rows
    ]
    graded = [t for t in topics if t["success_rate"] is not None]
    weak = [t["topic"] for t in graded if t["success_rate"] < 50][:3]
    strong = [t["topic"] for t in graded if t["success_rate"] >= 75][:3]

    return {"weak": weak, "strong": strong, "topics": topics}


async def get_diagnostic_report(db: AsyncSession, user_id: str) -> dict:
    """Post-session style diagnostic — LLM-summarized version of the topic
    breakdown, meant to be shown after an interview/PYQ session ends."""
    breakdown = await get_topic_breakdown(db, user_id)

    if not breakdown["topics"]:
        return {
            "strong_summary": "No graded attempts yet.",
            "weak_summary": "Complete a mock interview or code review to start building your profile.",
            "recommendation": "Try a mock interview on a topic you're comfortable with first.",
            "breakdown": breakdown,
        }

    topic_lines = "\n".join(
        f"- {t['topic']}: {t['attempts']} attempts, "
        f"{t['success_rate'] if t['success_rate'] is not None else 'ungraded'}% success"
        for t in breakdown["topics"]
    )

    llm_result = {}
    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[{"role": "user", "content": DIAGNOSTIC_PROMPT.format(topic_lines=topic_lines)}],
            temperature=0.4,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        llm_result = json.loads(match.group(0)) if match else {}
    except Exception as e:
        logger.error(f"Diagnostic report LLM summary failed: {e}")

    return {
        "strong_summary": llm_result.get("strong_summary", f"Strong in: {', '.join(breakdown['strong']) or 'building up data'}"),
        "weak_summary": llm_result.get("weak_summary", f"Needs work: {', '.join(breakdown['weak']) or 'building up data'}"),
        "recommendation": llm_result.get("recommendation", "Keep practicing consistently across topics."),
        "breakdown": breakdown,
    }