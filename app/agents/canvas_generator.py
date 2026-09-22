"""
Hybrid LangGraph-style canvas code generator.

Decision tree:
  1. validate_labels  — ast.parse() each label; collect "dirty" ones
  2a. If no dirty labels → assemble_direct (pure rule engine, zero LLM)
  2b. If dirty labels  → llm_clean (one batched Groq call for dirty only)
                       → assemble_with_cleaned (rule engine on cleaned labels)

"Control flow is always deterministic. LLM only translates natural language
 labels into valid Python fragments — it never writes the full program."
"""
import ast
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from groq import AsyncGroq
from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Data model (mirrors what Flutter sends) ───────────────────────────
@dataclass
class CanvasNode:
    id: str
    type: str       # start | end | process | decision | input
    label: str
    x: float = 0.0
    y: float = 0.0


@dataclass
class CanvasConnection:
    from_node_id: str
    to_node_id: str
    from_port_id: str = ""
    to_node_port_id: str = ""
    label: str = ""           # YES / NO


@dataclass
class GeneratorState:
    nodes: list[CanvasNode]
    connections: list[CanvasConnection]
    language: str = "python"
    dirty_node_ids: list[str] = field(default_factory=list)
    cleaned_labels: dict[str, str] = field(default_factory=dict)   # node_id → clean label
    generated_code: str = ""
    used_llm: bool = False
    llm_badge_nodes: list[str] = field(default_factory=list)        # node ids that needed LLM
    error: Optional[str] = None


# ── Step 1: validate labels with Python's own parser ─────────────────
async def validate_labels(state: GeneratorState) -> GeneratorState:
    dirty = []
    for node in state.nodes:
        label = node.label.strip()
        if not label or label.upper() in ("START", "END"):
            continue

        test_label = _normalize_for_parse(label)

        if node.type == "decision":
            low = test_label.lower()
            if low.startswith("for ") or low.startswith("while "):
                # Loop-style decision: valid only as a compound statement, so
                # parse it with a dummy body rather than as a bare expression.
                mode = "exec"
                test_label = f"{test_label.rstrip(':')}:\n    pass"
            else:
                mode = "eval"
        else:
            mode = "exec"

        try:
            ast.parse(test_label, mode=mode)
        except SyntaxError:
            dirty.append(node.id)

    state.dirty_node_ids = dirty
    logger.info(f"Canvas validate: {len(state.nodes)} nodes, {len(dirty)} dirty")
    return state


def _normalize_for_parse(label: str) -> str:
    """Light normalization — enough to not over-trigger LLM for common patterns."""
    s = label
    # Multi-line statements joined with newline are fine
    s = s.replace("\\n", "\n")
    # Strip trailing colons that rule-engine will add anyway
    s = s.rstrip(":")
    # Simple ellipsis variants → Python ellipsis literal (won't run but parses)
    s = re.sub(r'\.{2,}', '...', s)
    return s


# ── Step 2a: assemble without LLM ─────────────────────────────────────
async def assemble_direct(state: GeneratorState) -> GeneratorState:
    state.generated_code = _build_code(state.nodes, state.connections, state.cleaned_labels)
    state.used_llm = False
    return state


# ── Step 2b: LLM clean (batched, one call) ───────────────────────────
_CLEAN_PROMPT = """You are a code-generation assistant. The user has drawn a flowchart 
with pseudocode or natural language labels. Translate EACH label into valid 
{language} syntax. Be minimal — do NOT add logic that wasn't implied. 
Preserve variable names where possible.

Node types:
- process: one or more executable statements (joined by \\n)
- decision: EITHER a boolean expression OR a loop header — see rules below
- input: just a variable name (e.g. 'x')
- start/end: ignore these

CRITICAL rules for `decision` nodes:
- If the label expresses ITERATION (e.g. "for i = 2 to n", "repeat while x > 0",
  "loop i from 1 to 10"), return a COMPLETE loop header WITHOUT the trailing colon:
    "for i = 2 to n"        -> "for i in range(2, n + 1)"
    "loop i from 0 to n-1"  -> "for i in range(0, n)"
    "while x > 0"           -> "while x > 0"
- If the label is a plain TEST (e.g. "is x > 0?", "arr is empty"), return only the
  boolean expression with no 'if' and no colon:
    "is wt[i-1] <= w ?"     -> "wt[i - 1] <= w"
- Never convert a loop into a range-check like "i >= 2 and i <= n". If the user
  wrote "for", the output MUST start with "for" or "while".

Labels to clean (JSON array):
{labels_json}

Return ONLY a JSON object mapping each node_id to its cleaned label:
{{
  "node_id_1": "cleaned label",
  "node_id_2": "cleaned label"
}}"""


async def llm_clean(state: GeneratorState) -> GeneratorState:
    if not state.dirty_node_ids:
        return state

    dirty_nodes = [n for n in state.nodes if n.id in state.dirty_node_ids]
    labels_json = json.dumps([
        {"id": n.id, "type": n.type, "label": n.label}
        for n in dirty_nodes
    ], indent=2)

    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[{"role": "user", "content": _CLEAN_PROMPT.format(
                language=state.language, labels_json=labels_json
            )}],
            temperature=0.1,
            max_tokens=800,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            cleaned = json.loads(match.group(0))
            state.cleaned_labels = {
                k: str(v) for k, v in cleaned.items()
                if isinstance(k, str) and isinstance(v, str)
            }
            state.llm_badge_nodes = list(state.cleaned_labels.keys())
            state.used_llm = True
            logger.info(f"LLM cleaned {len(state.cleaned_labels)} labels")
    except Exception as e:
        logger.error(f"LLM clean failed: {e}")
        # Fallback: use original labels — at least partial code is generated
        state.error = f"LLM unavailable, using raw labels: {e}"

    return state


async def assemble_with_cleaned(state: GeneratorState) -> GeneratorState:
    state.generated_code = _build_code(state.nodes, state.connections, state.cleaned_labels)
    return state


# ── Main entry point (LangGraph-style sequential runner) ──────────────
async def generate(
    nodes_raw: list[dict],
    connections_raw: list[dict],
    language: str = "python",
) -> dict:
    """
    nodes_raw: [{"id":..., "type":..., "label":..., "x":..., "y":...}]
    connections_raw: [{"fromNodeId":..., "toNodeId":..., "label":...}]
    """
    if not nodes_raw:
        return {"code": "", "used_llm": False, "llm_badge_nodes": [], "error": None}

    nodes = [CanvasNode(
        id=n["id"], type=n["type"], label=n.get("label", ""),
        x=float(n.get("x", 0)), y=float(n.get("y", 0)),
    ) for n in nodes_raw]

    connections = [CanvasConnection(
        from_node_id=c["fromNodeId"], to_node_id=c["toNodeId"],
        label=c.get("label", ""),
    ) for c in connections_raw]

    logger.info(
        f"Canvas generate: {len(nodes)} nodes, {len(connections)} connections. "
        f"node_ids={[n.id for n in nodes]} "
        f"edges={[(c.from_node_id, c.to_node_id) for c in connections]}"
    )

    state = GeneratorState(nodes=nodes, connections=connections, language=language)

    # Step 1 — validate
    state = await validate_labels(state)

    # Step 2 — branch
    if not state.dirty_node_ids:
        state = await assemble_direct(state)
    else:
        state = await llm_clean(state)
        state = await assemble_with_cleaned(state)

    logger.info(
        f"Canvas generate result: {len(state.generated_code)} chars, "
        f"used_llm={state.used_llm}, dirty={len(state.dirty_node_ids)}"
    )

    return {
        "code": state.generated_code,
        "used_llm": state.used_llm,
        "llm_badge_nodes": state.llm_badge_nodes,
        "dirty_count": len(state.dirty_node_ids),
        "error": state.error,
    }


# ── Deterministic rule-engine (Python) ───────────────────────────────
def _build_code(
    nodes: list[CanvasNode],
    connections: list[CanvasConnection],
    cleaned_labels: dict[str, str],
) -> str:
    if not nodes:
        return ""

    def effective_label(node: CanvasNode) -> str:
        return cleaned_labels.get(node.id, node.label).strip()

    # Build adjacency: node_id → [(edge_label, target_node_id)]
    adj: dict[str, list[tuple[str, str]]] = {}
    for c in connections:
        adj.setdefault(c.from_node_id, [])
        adj[c.from_node_id].append((c.label, c.to_node_id))

    node_map = {n.id: n for n in nodes}

    # Find start node
    all_targets = {c.to_node_id for c in connections}
    try:
        start = next(n for n in nodes if n.type == "start")
    except StopIteration:
        try:
            start = next(n for n in nodes if n.id not in all_targets)
        except StopIteration:
            start = nodes[0]

    lines: list[str] = []
    visited: set[str] = set()
    _traverse(start, node_map, adj, lines, visited, 0, effective_label)

    # Fallback: traversal produced nothing (e.g. shapes not actually wired
    # up, or the start node has no outgoing edges). Rather than returning an
    # empty editor, emit every non-terminal node top-to-bottom by Y position
    # so the student still gets usable code they can fix by hand.
    if not [ln for ln in lines if ln.strip()]:
        logger.warning(
            "Canvas traversal produced no lines — falling back to positional order. "
            f"nodes={len(nodes)} connections={len(connections)}"
        )
        ordered = sorted(nodes, key=lambda n: n.y)
        for n in ordered:
            if n.type in ("start", "end"):
                continue
            lbl = effective_label(n)
            if not lbl:
                continue
            if n.type == "decision":
                low = lbl.lower()
                if low.startswith("for ") or low.startswith("while "):
                    lines.append(f"{lbl.rstrip(':')}:")
                else:
                    lines.append(f"if {lbl.rstrip(':')}:")
                lines.append("    pass")
            elif n.type == "input":
                lines.append(f'{lbl} = int(input("Enter {lbl}: "))')
            else:
                for stmt in lbl.split("\n"):
                    if stmt.strip():
                        lines.append(stmt.strip())

    return "\n".join(lines)


def _traverse(
    node: CanvasNode,
    node_map: dict,
    adj: dict,
    lines: list,
    visited: set,
    depth: int,
    label_fn,
) -> None:
    if node.id in visited:
        return
    visited.add(node.id)

    indent = "    " * depth
    label = label_fn(node)

    if node.type == "start":
        label_lower = label.lower()
        if label_lower not in ("start", ""):
            # Treat as function definition
            parts = label.split()
            fname = parts[0]
            params = ", ".join(parts[1:]) if len(parts) > 1 else ""
            lines.append(f"def {fname}({params}):")
            _traverse_children(node, node_map, adj, lines, visited, depth + 1, label_fn)
            return
        _traverse_children(node, node_map, adj, lines, visited, depth, label_fn)
        return

    if node.type == "end":
        label_lower = label.lower()
        if label_lower not in ("end", ""):
            lines.append(f"{indent}return {label}")
        return

    if node.type == "decision":
        cond = label.rstrip(":").strip()
        edges = adj.get(node.id, [])
        yes_edge = next((e for e in edges if e[0] in ("YES", "", "yes")), None)
        no_edge = next((e for e in edges if e[0] in ("NO", "no")), None)
        if yes_edge is None and edges:
            yes_edge = edges[0]
        if no_edge is None and len(edges) > 1:
            no_edge = edges[1]

        # A decision whose label is actually a loop header ("for ...", "while ...")
        # must emit a real loop — the YES branch becomes the loop BODY and the
        # NO branch continues AFTER the loop at the same indent as the header.
        # Without this, "for i = 2 to n" degrades into a one-shot if/else.
        is_loop = cond.lower().startswith("for ") or cond.lower().startswith("while ")

        if is_loop:
            lines.append(f"{indent}{cond}:")
            if yes_edge and yes_edge[1] in node_map:
                _traverse(node_map[yes_edge[1]], node_map, adj, lines, visited, depth + 1, label_fn)
            else:
                lines.append(f"{indent}    pass")
            if no_edge and no_edge[1] in node_map:
                _traverse(node_map[no_edge[1]], node_map, adj, lines, visited, depth, label_fn)
            return

        lines.append(f"{indent}if {cond}:")
        if yes_edge and yes_edge[1] in node_map:
            _traverse(node_map[yes_edge[1]], node_map, adj, lines, visited, depth + 1, label_fn)
        else:
            lines.append(f"{indent}    pass")

        if no_edge and no_edge[1] in node_map:
            lines.append(f"{indent}else:")
            _traverse(node_map[no_edge[1]], node_map, adj, lines, visited, depth + 1, label_fn)
        return

    if node.type == "process":
        # Support multi-line labels (user pressed enter in editor)
        for stmt in label.split("\n"):
            stmt = stmt.strip()
            if stmt:
                lines.append(f"{indent}{stmt}")
        _traverse_children(node, node_map, adj, lines, visited, depth, label_fn)
        return

    if node.type == "input":
        varname = label if label else "x"
        lines.append(f'{indent}{varname} = int(input("Enter {varname}: "))')
        _traverse_children(node, node_map, adj, lines, visited, depth, label_fn)
        return


def _traverse_children(
    node: CanvasNode, node_map: dict, adj: dict,
    lines: list, visited: set, depth: int, label_fn,
) -> None:
    for _, target_id in adj.get(node.id, []):
        if target_id in node_map and target_id not in visited:
            _traverse(node_map[target_id], node_map, adj, lines, visited, depth, label_fn)