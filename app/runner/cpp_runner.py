import tempfile, os
from app.runner.sandbox import RunResult, _exec_subprocess


async def run(code: str) -> RunResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "main.cpp")
        out = os.path.join(tmpdir, "main")
        with open(src, "w") as f:
            f.write(code)
        compile_result = await _exec_subprocess(
            ["g++", src, "-o", out, "-std=c++17", "-lm"], cwd=tmpdir
        )
        if compile_result.exit_code != 0:
            return RunResult(
                stdout="",
                stderr="Compilation error:\n" + compile_result.stderr,
                exit_code=compile_result.exit_code,
                runtime_ms=compile_result.runtime_ms,
                memory_kb=0,
                timed_out=False,
            )
        return await _exec_subprocess([out], cwd=tmpdir)
