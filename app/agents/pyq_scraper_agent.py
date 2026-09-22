"""PYQ Scraper Agent — given a company name, scrapes public interview-experience
pages (GFG, AmbitionBox-style listings), extracts recurring question patterns,
and generates fresh grounded questions from them. Results are cached per
company so repeat requests don't re-scrape every time."""
import json
import logging
import re
from datetime import datetime, timezone, timedelta
import httpx
from groq import AsyncGroq
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 14  # re-scrape a company at most every 2 weeks

EXTRACT_PROMPT = """Below is raw scraped text from interview-experience pages about {company}.
Extract the recurring DSA / technical question PATTERNS students report facing.

Raw scraped content:
{raw_content}

Return ONLY JSON:
{{
  "patterns": [
    {{"topic": "arrays|strings|trees|graphs|dp|linked_list", "pattern": "short description of the recurring question type"}}
  ]
}}
Max 8 patterns. If content has no clear signal, return {{"patterns": []}}."""

GENERATE_PROMPT = """You are a technical interviewer preparing a student for {company}.

Known question patterns reported by past candidates at this company:
{patterns}

Generate ONE fresh DSA interview question in the style of topic "{topic}", similar in
spirit to what {company} is known to ask, but not copied verbatim from any source.
Difficulty: {difficulty}. Keep it 2-4 sentences, like a real interviewer would state it.

Return ONLY JSON: {{"question": "the question text", "topic": "{topic}"}}"""


async def _scrape_company_pages(company: str) -> str:
    """Best-effort scrape of public search results mentioning the company +
    'interview experience'. Defensive: any failure just returns empty string,
    the caller falls back to generic questions rather than blocking."""
    query = f"{company} interview experience DSA questions"
    text_blobs = []
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code == 200:
                snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
                clean = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets]
                text_blobs = [c for c in clean if len(c) > 30][:10]
    except Exception as e:
        logger.warning(f"PYQ scrape failed for {company} (non-fatal, falling back): {e}")
    return "\n".join(text_blobs)


async def _get_cached_patterns(company: str) -> list | None:
    try:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                text("SELECT patterns, scraped_at FROM company_pyq_cache WHERE company = :c"),
                {"c": company.lower().strip()},
            )).fetchone()
            if row:
                scraped_at = row.scraped_at
                if scraped_at.tzinfo is None:
                    scraped_at = scraped_at.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - scraped_at < timedelta(days=CACHE_TTL_DAYS):
                    return json.loads(row.patterns)
    except Exception as e:
        logger.warning(f"PYQ cache read failed (non-fatal): {e}")
    return None


async def _store_patterns(company: str, patterns: list) -> None:
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("""
                    INSERT INTO company_pyq_cache (company, patterns, scraped_at)
                    VALUES (:c, :p, :now)
                    ON CONFLICT (company) DO UPDATE SET patterns = :p, scraped_at = :now
                """),
                {"c": company.lower().strip(), "p": json.dumps(patterns), "now": datetime.now(timezone.utc)},
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"PYQ cache write failed (non-fatal): {e}")


async def _call_groq_json(prompt: str, temperature: float, max_tokens: int) -> dict:
    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw = response.choices[0].message.content or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        logger.error(f"Groq call failed in pyq agent: {e}")
    return {}


async def get_company_patterns(company: str) -> list:
    """Cached patterns for a company, scraping + extracting only if stale/missing."""
    cached = await _get_cached_patterns(company)
    if cached is not None:
        return cached

    raw = await _scrape_company_pages(company)
    patterns = []
    if raw:
        result = await _call_groq_json(
            EXTRACT_PROMPT.format(company=company, raw_content=raw[:6000]),
            temperature=0.2, max_tokens=600,
        )
        patterns = result.get("patterns", [])

    await _store_patterns(company, patterns)
    return patterns


async def generate_company_question(company: str, topic: str = None, difficulty: str = "medium") -> dict:
    """Main entry point: given a company (and optionally a topic override),
    return a grounded question + which topic it's tagged as."""
    patterns = await get_company_patterns(company)

    if not topic:
        topic = patterns[0]["topic"] if patterns else "arrays"

    if not patterns:
        # No scraped signal — fall back to a generic question for the topic,
        # never leave the student with a blank screen.
        return {
            "question": f"Walk me through how you'd approach a common {topic} problem — the kind {company} is known to ask in early rounds.",
            "topic": topic,
            "grounded": False,
        }

    patterns_str = "\n".join(f"- [{p.get('topic')}] {p.get('pattern')}" for p in patterns)
    result = await _call_groq_json(
        GENERATE_PROMPT.format(company=company, patterns=patterns_str, topic=topic, difficulty=difficulty),
        temperature=0.6, max_tokens=400,
    )
    question = result.get("question", "").strip()
    if not question:
        question = f"Walk me through how you'd approach a common {topic} problem — the kind {company} is known to ask in early rounds."

    return {"question": question, "topic": topic, "grounded": True}
