"""Code Example Agent — for when a student explicitly asks for working code
("give me code for X", "show me the implementation of Y"). Deliberately
NOT Socratic — this is the one path in the app that hands over full code,
kept separate from the tutor's hint-only philosophy in graph.py."""
import logging
from groq import AsyncGroq
from app.core.config import settings

logger = logging.getLogger(__name__)

CODE_PROMPT = """A student explicitly asked for working code: "{message}"

Give a complete, correct, well-commented implementation. Use a single fenced
code block with the language tag (e.g. ```python). Briefly explain the
approach in 2-3 sentences before the code — but always include the actual
code, don't just describe it.

Language: {language}"""


async def generate_code_example(message: str, language: str = "python") -> dict:
    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": CODE_PROMPT.format(message=message, language=language)}],
            temperature=0.3,
            max_tokens=1200,
        )
        text = response.choices[0].message.content or ""
        if not text.strip():
            raise ValueError("empty response")
        return {"response": text.strip()}
    except Exception as e:
        logger.error(f"Code example generation failed: {e}")
        return {"response": "I couldn't generate that right now — try rephrasing or ask again in a moment."}
