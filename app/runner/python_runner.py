import tempfile, os, sys
from app.runner.sandbox import RunResult, _exec_subprocess


async def run(code: str) -> RunResult:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code)
        fpath = f.name
    try:
        return await _exec_subprocess(
            [sys.executable, "-u", fpath],
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    finally:
        os.unlink(fpath)
