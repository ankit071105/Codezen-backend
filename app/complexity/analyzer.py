from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ComplexityResult:
    time_complexity: str
    space_complexity: str
    confidence: str
    explanation: str
    suggestions: list[str]


def analyze_complexity(code: str, language: str) -> ComplexityResult:
    try:
        if language.lower() == "python":
            return _analyze_python(code)
        elif language.lower() in ("c", "cpp", "c++"):
            return _analyze_c_family(code)
        elif language.lower() == "java":
            return _analyze_java(code)
        else:
            return _fallback_analysis(code)
    except Exception as e:
        logger.error(f"Complexity analysis error: {e}")
        return ComplexityResult(
            time_complexity="O(?)",
            space_complexity="O(?)",
            confidence="low",
            explanation="Could not analyze complexity.",
            suggestions=[],
        )


def _count_loop_nesting(lines: list[str], loop_keywords: list[str]) -> int:
    max_depth = 0
    current_depth = 0
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(kw) for kw in loop_keywords):
            current_depth += 1
            max_depth = max(max_depth, current_depth)
        elif stripped.startswith("return") or (stripped == "" and current_depth > 0):
            pass
    return max_depth


def _detect_recursion(code: str, func_names: list[str]) -> bool:
    for name in func_names:
        body_start = code.find(name)
        if body_start == -1:
            continue
        body = code[body_start + len(name):]
        if name + "(" in body:
            return True
    return False


def _extract_python_func_names(code: str) -> list[str]:
    import re
    return re.findall(r"def\s+(\w+)\s*\(", code)


def _extract_java_func_names(code: str) -> list[str]:
    import re
    return re.findall(r"(?:public|private|protected|static).*?\s+(\w+)\s*\(", code)


def _depth_to_time_complexity(depth: int, has_recursion: bool, has_log: bool) -> tuple[str, str]:
    if has_recursion and has_log:
        return "O(n log n)", "medium"
    if has_recursion:
        return "O(2^n)", "medium"
    if has_log:
        if depth <= 1:
            return "O(log n)", "high"
        return "O(n log n)", "high"
    mapping = {0: ("O(1)", "high"), 1: ("O(n)", "high"), 2: ("O(n²)", "high"), 3: ("O(n³)", "high")}
    return mapping.get(depth, (f"O(n^{depth})", "medium"))


def _detect_log_pattern(code: str) -> bool:
    log_indicators = ["// 2", "left + right", "mid = ", "binary", "half", "lo + hi", "low + high"]
    return any(ind in code.lower() for ind in log_indicators)


def _space_complexity(code: str) -> str:
    code_lower = code.lower()
    if any(kw in code_lower for kw in ["matrix", "[][]", "2d", "grid"]):
        return "O(n²)"
    if any(kw in code_lower for kw in ["list", "array", "vector", "dict", "map", "set", "stack", "queue", "append"]):
        return "O(n)"
    return "O(1)"


def _build_suggestions(time_c: str, space_c: str, has_recursion: bool) -> list[str]:
    suggestions = []
    if time_c in ("O(n²)", "O(n³)"):
        suggestions.append("Consider using a hash map or sorting to reduce to O(n log n)")
        suggestions.append("Look into divide and conquer strategies")
    if time_c == "O(2^n)" and has_recursion:
        suggestions.append("Consider memoization or dynamic programming to reduce to O(n)")
    if space_c == "O(n²)":
        suggestions.append("Try in-place algorithms to reduce space usage")
    return suggestions


def _analyze_python(code: str) -> ComplexityResult:
    lines = code.split("\n")
    loop_kws = ["for ", "while "]
    depth = _count_loop_nesting(lines, loop_kws)
    func_names = _extract_python_func_names(code)
    has_recursion = _detect_recursion(code, func_names)
    has_log = _detect_log_pattern(code)
    code_lower = code.lower()

    # Detect memoization — overrides exponential recursion
    has_memo = any(kw in code_lower for kw in [
        "lru_cache", "cache", "@cache", "memo", "seen", "visited",
        "dp[", "dp =", "table[", "cache[", "memo[", "stored",
    ])

    # Detect DP table (overrides recursion complexity)
    has_dp_table = any(kw in code_lower for kw in [
        "dp = [", "dp=[", "dp = {", "table = [",
        "for i in range", "dp[i]", "dp[i-1]",
    ])

    # Detect set/dict for O(n) solutions
    has_hashmap = any(kw in code_lower for kw in [
        "set()", "{}", "dict()", "defaultdict", "counter(",
        "hashmap", "seen = {", "freq =",
    ])

    if has_recursion and has_memo:
        # Memoized recursion = O(n) typically
        time_c, confidence = "O(n)", "high"
    elif has_dp_table and depth <= 1:
        time_c, confidence = "O(n)", "high"
    elif has_dp_table and depth == 2:
        time_c, confidence = "O(n²)", "high"
    elif has_hashmap and depth <= 1 and not has_recursion:
        time_c, confidence = "O(n)", "high"
    else:
        time_c, confidence = _depth_to_time_complexity(depth, has_recursion, has_log)

    space_c = _space_complexity(code)
    suggestions = _build_suggestions(time_c, space_c, has_recursion)

    return ComplexityResult(
        time_complexity=time_c,
        space_complexity=space_c,
        confidence=confidence,
        explanation=f"Detected {'memoization, ' if has_memo else ''}{'DP table, ' if has_dp_table else ''}{'recursion, ' if has_recursion else ''}{'logarithmic, ' if has_log else ''}{depth} loop level(s).",
        suggestions=suggestions,
    )


def _analyze_c_family(code: str) -> ComplexityResult:
    lines = code.split("\n")
    loop_kws = ["for (", "for(", "while (", "while("]
    depth = _count_loop_nesting(lines, loop_kws)
    has_log = _detect_log_pattern(code)
    has_recursion = False

    import re
    func_names = re.findall(r"\w+\s+(\w+)\s*\([^)]*\)\s*\{", code)
    if func_names:
        has_recursion = _detect_recursion(code, func_names)

    time_c, confidence = _depth_to_time_complexity(depth, has_recursion, has_log)
    space_c = _space_complexity(code)
    suggestions = _build_suggestions(time_c, space_c, has_recursion)

    return ComplexityResult(
        time_complexity=time_c,
        space_complexity=space_c,
        confidence=confidence,
        explanation=f"Detected {depth} nested loop level(s){'with recursion' if has_recursion else ''}.",
        suggestions=suggestions,
    )


def _analyze_java(code: str) -> ComplexityResult:
    return _analyze_c_family(code)


def _fallback_analysis(code: str) -> ComplexityResult:
    lines = code.split("\n")
    depth = _count_loop_nesting(lines, ["for", "while"])
    time_c = ["O(1)", "O(n)", "O(n²)", "O(n³)"][min(depth, 3)]
    return ComplexityResult(
        time_complexity=time_c,
        space_complexity=_space_complexity(code),
        confidence="low",
        explanation="Basic analysis applied.",
        suggestions=[],
    )