import sys
import ast
import json
import tempfile
import os
import asyncio
import traceback
from typing import Optional


DEBUGGER_WRAPPER = '''
import sys
import json
import copy

_trace_log = []
_locals_history = {}

def _safe_repr(v):
    try:
        if isinstance(v, (int, float, bool, str, type(None))):
            return v
        elif isinstance(v, (list, tuple)):
            return [_safe_repr(i) for i in v[:10]]
        elif isinstance(v, dict):
            return {str(k): _safe_repr(v2) for k, v2 in list(v.items())[:10]}
        elif isinstance(v, set):
            return list(v)[:10]
        else:
            return str(v)
    except:
        return str(type(v))

def _tracer(frame, event, arg):
    if event not in ("line", "return", "exception"):
        return _tracer
    if frame.f_code.co_filename != "<string>":
        return _tracer
    
    local_vars = {}
    for k, v in frame.f_locals.items():
        if not k.startswith("_"):
            local_vars[k] = _safe_repr(v)
    
    entry = {
        "line": frame.f_lineno,
        "event": event,
        "locals": local_vars,
        "stdout": "",
    }
    
    if event == "exception" and arg:
        entry["error"] = str(arg[1])
    
    _trace_log.append(entry)
    return _tracer

import io
_stdout_buf = io.StringIO()
_original_stdout = sys.stdout
sys.stdout = _stdout_buf

sys.settrace(_tracer)
try:
    exec(compile(open("/tmp/__cz_code__.py").read(), "<string>", "exec"))
except Exception as e:
    _trace_log.append({"line": -1, "event": "error", "locals": {}, "error": str(e), "stdout": ""})
finally:
    sys.settrace(None)
    sys.stdout = _original_stdout

captured = _stdout_buf.getvalue()
if _trace_log:
    _trace_log[-1]["stdout"] = captured

print(json.dumps({"trace": _trace_log, "output": captured}))
'''


async def debug_python(code: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        code_file = os.path.join(tmpdir, "__cz_code__.py")
        wrapper_file = os.path.join(tmpdir, "wrapper.py")
        
        # Copy to /tmp for wrapper access
        with open("/tmp/__cz_code__.py", "w") as f:
            f.write(code)
        
        with open(wrapper_file, "w") as f:
            f.write(DEBUGGER_WRAPPER)
        
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, wrapper_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=15
                )
                stdout = stdout_b.decode("utf-8", errors="replace")
                stderr = stderr_b.decode("utf-8", errors="replace")
                
                if stdout.strip():
                    try:
                        result = json.loads(stdout.strip())
                        return {
                            "success": True,
                            "trace": result.get("trace", []),
                            "output": result.get("output", ""),
                            "error": None,
                        }
                    except json.JSONDecodeError:
                        pass
                
                return {
                    "success": False,
                    "trace": [],
                    "output": "",
                    "error": stderr or "Failed to parse debug output",
                }
            except asyncio.TimeoutError:
                proc.kill()
                return {"success": False, "trace": [], "output": "", "error": "Debug timed out (15s)"}
        except Exception as e:
            return {"success": False, "trace": [], "output": "", "error": str(e)}
        finally:
            try:
                os.unlink("/tmp/__cz_code__.py")
            except:
                pass
