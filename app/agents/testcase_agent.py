"""Test Case Generator Agent — generates edge cases for a function and runs them
against the student's code using the existing sandbox.

Fixed from the original: the model used to be asked to re-emit the student's
FULL code inside every one of 5 test cases ("code_to_run": full runnable
snippet including student's function"). For anything non-trivial (e.g. a
class with several methods) that blows past max_tokens, truncates mid-JSON,
and silently returns empty results every time.

New approach: the model only generates a short call+print snippet per test
case. The server composes the runnable snippet as
    student_code + "\n\n" + call_snippet
itself. Smaller model output, no duplication, no truncation, same behavior.
"""
import json
import logging
import re
from groq import AsyncGroq
from app.core.config import settings
from app.runner.sandbox import run_code

logger = logging.getLogger(__name__)

GEN_PROMPT = """You are a test case generator for a {language} function/class.

Problem: {problem_description}

Student's code (already defined, do NOT repeat it in your answer):
```
{code}
```

Generate 5 test cases that would meaningfully test this code:
- 1 normal/happy-path case
- 2 edge cases (empty input, single element, boundary values)
- 1 negative/invalid input case if applicable
- 1 large/stress case if applicable

For each test case, give ONLY a short call_snippet — a few lines that call the
already-defined function/class and print the result. Do NOT redefine or repeat
the student's function/class — assume it already exists above your snippet.

Return ONLY this JSON:
{{
  "test_cases": [
    {{"name": "Normal case", "description": "what this tests", "call_snippet": "short code that calls the existing function and prints the result"}}
  ]
}}"""


def _clean_raw(raw: str) -> str:
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"```json\s*|\s*```", "", raw)
    return raw.strip()


async def generate_test_cases(code: str, language: str, problem_description: str) -> dict:
    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[{
                "role": "user",
                "content": GEN_PROMPT.format(language=language, problem_description=problem_description, code=code),
            }],
            temperature=0.3,
            max_tokens=900,  # small now — only 5 short call snippets, not 5x full code
        )
        raw = response.choices[0].message.content or ""
        cleaned = _clean_raw(raw)
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not match:
            logger.warning(f"Test case generation: no JSON found in response. Raw: {raw[:300]!r}")
            return {"test_cases": [], "results": [], "error": "Could not parse test cases from model response."}

        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as je:
            logger.warning(f"Test case generation: JSON parse failed ({je}). Raw: {raw[:500]!r}")
            return {"test_cases": [], "results": [], "error": "Model response was malformed — try again."}

        test_cases = parsed.get("test_cases", [])
        if not test_cases:
            return {"test_cases": [], "results": [], "error": "Model returned no test cases."}

        # Compose full runnable snippet ourselves: student's code once + each call snippet
        results = []
        for tc in test_cases[:5]:
            call_snippet = tc.get("call_snippet", "").strip()
            if not call_snippet:
                continue
            full_snippet = f"{code}\n\n{call_snippet}"
            try:
                run_result = await run_code(language, full_snippet)
                results.append({
                    "name": tc.get("name", "Test"),
                    "description": tc.get("description", ""),
                    "stdout": run_result.stdout,
                    "stderr": run_result.stderr,
                    "passed": run_result.exit_code == 0 and not run_result.timed_out,
                    "runtime_ms": run_result.runtime_ms,
                })
            except Exception as run_e:
                logger.error(f"Test case execution failed for '{tc.get('name')}': {run_e}")
                results.append({
                    "name": tc.get("name", "Test"),
                    "description": tc.get("description", ""),
                    "stdout": "",
                    "stderr": str(run_e),
                    "passed": False,
                    "runtime_ms": 0,
                })

        return {"test_cases": test_cases, "results": results}

    except Exception as e:
        logger.error(f"Test case generation error: {e}")
        return {"test_cases": [], "results": [], "error": str(e)}