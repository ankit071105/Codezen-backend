import asyncio
import os
import tempfile
import time
import resource
import signal
from dataclasses import dataclass
from typing import Optional
from app.core.config import settings


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int
    runtime_ms: int
    memory_kb: int
    timed_out: bool


LANGUAGE_CONFIGS = {
    "python": {"ext": ".py", "runner": "python_runner"},
    "c":      {"ext": ".c",  "runner": "c_runner"},
    "cpp":    {"ext": ".cpp","runner": "cpp_runner"},
    "java":   {"ext": ".java","runner": "java_runner"},
}


async def run_code(language: str, code: str) -> RunResult:
    lang = language.lower()
    if lang not in LANGUAGE_CONFIGS:
        return RunResult(
            stdout="", stderr=f"Language '{language}' not supported",
            exit_code=1, runtime_ms=0, memory_kb=0, timed_out=False,
        )
    from app.runner import python_runner, c_runner, cpp_runner, java_runner
    runners = {
        "python": python_runner.run,
        "c":      c_runner.run,
        "cpp":    cpp_runner.run,
        "java":   java_runner.run,
    }
    return await runners[lang](code)


async def _exec_subprocess(
    cmd: list[str],
    input_data: Optional[str] = None,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
) -> RunResult:
    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if input_data else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input_data.encode() if input_data else None),
                timeout=settings.RUNNER_TIMEOUT_SECONDS,
            )
            elapsed = int((time.monotonic() - start) * 1000)
            return RunResult(
                stdout=stdout_b.decode("utf-8", errors="replace")[:50000],
                stderr=stderr_b.decode("utf-8", errors="replace")[:10000],
                exit_code=proc.returncode or 0,
                runtime_ms=elapsed,
                memory_kb=0,
                timed_out=False,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            elapsed = int((time.monotonic() - start) * 1000)
            return RunResult(
                stdout="",
                stderr=f"Execution timed out after {settings.RUNNER_TIMEOUT_SECONDS}s",
                exit_code=124,
                runtime_ms=elapsed,
                memory_kb=0,
                timed_out=True,
            )
    except Exception as e:
        return RunResult(
            stdout="", stderr=str(e), exit_code=1,
            runtime_ms=0, memory_kb=0, timed_out=False,
        )
