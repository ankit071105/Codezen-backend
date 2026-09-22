import re
from dataclasses import dataclass
from typing import Optional


BLOCKED_TOPICS = [
    "bomb", "weapon", "malware", "virus", "ransomware",
    "ddos", "phishing", "crack password",
]

CHEAT_PATTERNS = [
    r"do my homework",
    r"complete (my|this) assignment",
    r"write my (exam|test) answer",
    r"bypass (the )?filter",
]

PII_PATTERNS = [
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    r"\b\d{10}\b",
    r"\b\d{12}\b",
]

PROMPT_INJECTION_PATTERNS = [
    r"ignore (previous|all|your) (instructions?|rules?|prompts?)",
    r"jailbreak",
    r"forget everything",
    r"new persona",
]

# Broad CS/programming keywords — be generous
CS_KEYWORDS = [
    "algorithm", "code", "function", "class", "variable", "loop",
    "recursion", "array", "list", "stack", "queue", "tree", "graph",
    "sort", "search", "complexity", "debug", "error", "program",
    "compile", "runtime", "memory", "pointer", "object", "method",
    "python", "java", "c++", "javascript", "c ", "linked list", "binary",
    "hash", "dynamic programming", "greedy", "backtracking", "big o",
    "time complexity", "space complexity", "syntax", "logic", "string",
    "integer", "float", "boolean", "dict", "map", "set", "tuple",
    "exception", "import", "module", "library", "api", "database",
    "palindrome", "fibonacci", "factorial", "prime", "subsequence",
    "substring", "permutation", "combination", "matrix", "vector",
    "node", "edge", "vertex", "path", "cycle", "traversal", "bfs", "dfs",
    "heap", "trie", "segment", "bit", "bitwise", "operator", "loop",
    "while", "for", "if", "else", "return", "print", "output", "input",
    "implement", "write", "create", "build", "make", "give", "show",
    "explain", "what is", "how to", "how does", "difference between",
    "example", "sample", "solution", "approach", "technique", "method",
    "data structure", "oop", "interface", "abstract", "inheritance",
    "polymorphism", "encapsulation", "thread", "async", "concurrent",
    "sql", "query", "index", "join", "aggregate", "transaction",
    "regex", "pattern", "parsing", "tokenize", "compiler", "interpreter",
    "os", "process", "socket", "network", "http", "rest", "api",
    "git", "docker", "linux", "bash", "shell", "terminal",
    "test", "unit test", "debugging", "breakpoint", "trace", "stack trace",
    "overflow", "underflow", "null", "undefined", "nan", "infinity",
    "lcs", "dp", "memoization", "tabulation", "divide", "conquer",
    "brute force", "optimization", "efficient", "optimal",
]


@dataclass
class GuardrailResult:
    allowed: bool
    intent: str
    reason: Optional[str] = None
    sanitized_query: Optional[str] = None


def scrub_pii(text: str) -> str:
    for pattern in PII_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
    return text


def check_guardrails(query: str, code: Optional[str] = None) -> GuardrailResult:
    combined = (query + " " + (code or "")).lower()

    # Block prompt injection
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return GuardrailResult(
                allowed=False, intent="BLOCKED",
                reason="I can only help with programming and CS topics.",
            )

    # Block harmful topics
    for word in BLOCKED_TOPICS:
        if word in combined:
            return GuardrailResult(
                allowed=False, intent="BLOCKED",
                reason="This topic is outside CodeZen's scope. Ask me about code!",
            )

    # Block only explicit cheating (very specific patterns)
    for pattern in CHEAT_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return GuardrailResult(
                allowed=False, intent="BLOCKED",
                reason="I can help you understand and learn — but I won't do your assignment for you. Try asking me to explain the concept instead!",
            )

    clean_query = scrub_pii(query)

    # Check for code/error debugging intent
    has_code = bool(code and len(code.strip()) > 5)
    has_error = any(w in combined for w in [
        "error", "exception", "traceback", "segfault", "wrong output",
        "not working", "fix", "debug", "why is", "what's wrong", "issue",
        "problem", "fail", "crash", "bug",
    ])

    if has_error or has_code:
        return GuardrailResult(allowed=True, intent="DEBUG", sanitized_query=clean_query)

    # Check CS keywords — generous match (any one keyword = allow)
    has_cs = any(kw in combined for kw in CS_KEYWORDS)

    if has_cs:
        return GuardrailResult(allowed=True, intent="CONCEPT", sanitized_query=clean_query)

    # Default: if uncertain, allow it — better to help than block
    # Only block if clearly off-topic (no CS words at all AND short query)
    if len(query.split()) <= 3:
        return GuardrailResult(
            allowed=False, intent="OFF_TOPIC",
            reason="I'm CodeZen's AI assistant for programming and CS. What coding topic can I help you with?",
        )

    # Longer queries — give benefit of doubt
    return GuardrailResult(allowed=True, intent="CONCEPT", sanitized_query=clean_query)