import tempfile, os, re
from app.runner.sandbox import RunResult, _exec_subprocess


def _extract_class_name(code: str) -> str:
    match = re.search(r"public\s+class\s+(\w+)", code)
    return match.group(1) if match else "Main"


async def run(code: str) -> RunResult:
    class_name = _extract_class_name(code)
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, f"{class_name}.java")
        with open(src, "w") as f:
            f.write(code)
        compile_result = await _exec_subprocess(["javac", src], cwd=tmpdir)
        if compile_result.exit_code != 0:
            return RunResult(
                stdout="",
                stderr="Compilation error:\n" + compile_result.stderr,
                exit_code=compile_result.exit_code,
                runtime_ms=compile_result.runtime_ms,
                memory_kb=0,
                timed_out=False,
            )
        return await _exec_subprocess(
            ["java", "-cp", tmpdir, class_name], cwd=tmpdir
        )
