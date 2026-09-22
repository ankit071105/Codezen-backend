from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from groq import AsyncGroq
import logging

from app.core.config import settings
from app.agents.guardrails import check_guardrails, GuardrailResult
from app.rag.retriever import retrieve_context, check_qa_cache, store_qa_cache

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_RAG = """You are CodeZen AI — a helpful, knowledgeable computer science tutor.

Your job:
- Answer programming and CS questions clearly and accurately
- Provide working code examples when asked
- Explain concepts step by step
- Use the context below if relevant, otherwise use your own CS knowledge

Rules:
- Be educational and clear
- For coding questions: provide complete, working code with comments
- Keep answers focused and practical
- If asked to implement something, implement it fully

CONTEXT (use if relevant):
{context}
"""

SYSTEM_PROMPT_DEBUG = """You are CodeZen's debugging assistant.

Your job:
- Analyze the student's code and error carefully
- Identify what is wrong
- Give clear HINTS about what to fix — explain the concept behind the bug
- You CAN show a corrected snippet if needed to illustrate the fix
- Be helpful and educational

Student's code and error below:
"""


class AgentState(TypedDict):
    query: str
    code: Optional[str]
    language: Optional[str]
    room_id: Optional[str]
    user_id: Optional[str]
    intent: str
    guardrail_result: Optional[GuardrailResult]
    context_chunks: list
    final_response: Optional[str]
    cache_hit: bool
    error: Optional[str]


async def call_groq(system_prompt: str, user_message: str) -> str:
    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=1024,
            top_p=0.9,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq call failed: {e}")
        try:
            client2 = AsyncGroq(api_key=settings.GROQ_API_KEY)
            response2 = await client2.chat.completions.create(
                model="qwen/qwen3.6-27b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=1024,
            )
            return response2.choices[0].message.content
        except Exception as e2:
            logger.error(f"Groq fallback failed: {e2}")
            return "I'm having trouble connecting right now. Please try again in a moment."


async def router_node(state: AgentState) -> AgentState:
    result = check_guardrails(state["query"], state.get("code"))
    state["guardrail_result"] = result
    state["intent"] = result.intent
    if result.sanitized_query:
        state["query"] = result.sanitized_query
    return state


async def cache_check_node(state: AgentState) -> AgentState:
    if not state["guardrail_result"].allowed:
        state["cache_hit"] = False
        return state
    cached = await check_qa_cache(state["query"])
    if cached:
        state["final_response"] = cached
        state["cache_hit"] = True
    else:
        state["cache_hit"] = False
    return state


async def rag_agent_node(state: AgentState) -> AgentState:
    chunks = await retrieve_context(state["query"])
    state["context_chunks"] = chunks
    context_text = "\n\n".join(c["content"] for c in chunks) if chunks else "No specific context — use your CS knowledge."

    system = SYSTEM_PROMPT_RAG.format(context=context_text)
    answer = await call_groq(system, state["query"])
    state["final_response"] = answer
    await store_qa_cache(state["query"], answer)
    return state


async def debug_agent_node(state: AgentState) -> AgentState:
    chunks = await retrieve_context(state["query"] + " " + (state.get("code") or ""))
    state["context_chunks"] = chunks

    user_message = f"""Language: {state.get('language', 'unknown')}

Code:
```
{state.get('code', 'No code provided')}
```

Question/Error:
{state['query']}
"""
    answer = await call_groq(SYSTEM_PROMPT_DEBUG, user_message)
    state["final_response"] = answer
    return state


def route_after_guardrail(state: AgentState) -> str:
    if not state["guardrail_result"].allowed:
        return "blocked"
    return "cache_check"


def route_after_cache(state: AgentState) -> str:
    if state["cache_hit"]:
        return "done"
    if state["intent"] == "DEBUG":
        return "debug"
    return "rag"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("router", router_node)
    graph.add_node("cache_check", cache_check_node)
    graph.add_node("rag", rag_agent_node)
    graph.add_node("debug", debug_agent_node)
    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router", route_after_guardrail,
        {"blocked": END, "cache_check": "cache_check"},
    )
    graph.add_conditional_edges(
        "cache_check", route_after_cache,
        {"done": END, "rag": "rag", "debug": "debug"},
    )
    graph.add_edge("rag", END)
    graph.add_edge("debug", END)
    return graph.compile()


compiled_graph = build_graph()


async def run_agent(
    query: str,
    code: Optional[str] = None,
    language: Optional[str] = None,
    room_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    initial_state = AgentState(
        query=query, code=code, language=language,
        room_id=room_id, user_id=user_id,
        intent="", guardrail_result=None,
        context_chunks=[], final_response=None,
        cache_hit=False, error=None,
    )
    result = await compiled_graph.ainvoke(initial_state)
    guardrail = result.get("guardrail_result")
    if guardrail and not guardrail.allowed:
        return {
            "allowed": False, "intent": guardrail.intent,
            "response": guardrail.reason, "cache_hit": False, "sources": [],
        }
    return {
        "allowed": True, "intent": result.get("intent"),
        "response": result.get("final_response", ""),
        "cache_hit": result.get("cache_hit", False),
        "sources": [c.get("source", "") for c in result.get("context_chunks", [])],
    }