"""Supervisor -> {research, analysis} multi-agent graph.

The supervisor never touches LangGraph's END constant directly — it only ever writes
the string "FINISH" into AgentState.next_agent. route_supervisor() is the single place
that translates "FINISH" into END, per claude.md's design decision: routing logic and
LangGraph's own sentinel stay decoupled from the supervisor's own reasoning.
"""

import json
import operator
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent

from src.agents.tools import calculator, fetch_url, rag_query, web_search
from src.config import settings

_RESEARCH_TOOLS = [web_search, fetch_url]
_ANALYSIS_TOOLS = [calculator, rag_query]

_SUPERVISOR_SYSTEM_PROMPT = """You are a supervisor routing a task to one of two \
specialist agents, or finishing.

Agents:
- "research": web search and URL fetching. Use for questions needing current \
information or specific web content.
- "analysis": calculation and RAG lookups over previously-ingested documents. Use \
for math or questions about ingested documents.

Given the task and the conversation so far, decide what happens next. Route to \
FINISH once the conversation already contains enough information to answer the task.

Respond with ONLY a JSON object, no other text, in exactly this shape:
{"next": "research" | "analysis" | "FINISH", "answer": "<final answer, only when \
next is FINISH, otherwise empty string>"}
"""


class AgentState(TypedDict):
    messages: Annotated[list, operator.add]  # ALL messages — append only, never overwrite
    next_agent: str  # "research" | "analysis" | "FINISH"
    final_answer: str  # set by the supervisor when done
    iteration: int  # guard: incremented every supervisor call
    task: str  # original user task — never changes


def _llm(**kwargs) -> ChatOllama:
    return ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        **kwargs,
    )


def _guard_triggered_answer(state: AgentState) -> str:
    last_finding = state["messages"][-1].content if state["messages"] else "no progress made"
    return f"Reached the maximum number of iterations before finishing. Last known progress: {last_finding}"


def supervisor_node(state: AgentState) -> dict:
    iteration = state["iteration"] + 1

    if iteration >= settings.max_agent_iterations:
        return {
            "iteration": iteration,
            "next_agent": "FINISH",
            "final_answer": _guard_triggered_answer(state),
        }

    response = _llm(format="json").invoke(
        [
            SystemMessage(content=_SUPERVISOR_SYSTEM_PROMPT),
            HumanMessage(content=f"Task: {state['task']}"),
            *state["messages"],
        ]
    )

    try:
        decision = json.loads(response.content)
        next_agent = decision.get("next", "FINISH")
        answer = decision.get("answer", "")
    except (json.JSONDecodeError, TypeError):
        next_agent, answer = "FINISH", "error: supervisor returned invalid JSON"

    if next_agent not in ("research", "analysis", "FINISH"):
        next_agent, answer = "FINISH", answer or "error: supervisor returned an unknown route"

    return {
        "iteration": iteration,
        "next_agent": next_agent,
        "final_answer": answer if next_agent == "FINISH" else state["final_answer"],
    }


def _run_sub_agent(state: AgentState, tools: list, label: str) -> dict:
    agent = create_react_agent(_llm(), tools)
    recursion_limit = settings.max_react_steps * 2 + 1
    input_messages = [HumanMessage(content=state["task"]), *state["messages"]]

    try:
        result = agent.invoke(
            {"messages": input_messages}, config={"recursion_limit": recursion_limit}
        )
        finding = result["messages"][-1].content
    except GraphRecursionError:
        finding = f"{label} agent did not finish within {settings.max_react_steps} steps"

    return {"messages": [AIMessage(content=f"[{label}] {finding}")]}


def research_node(state: AgentState) -> dict:
    return _run_sub_agent(state, _RESEARCH_TOOLS, "research")


def analysis_node(state: AgentState) -> dict:
    return _run_sub_agent(state, _ANALYSIS_TOOLS, "analysis")


def route_supervisor(state: AgentState) -> str:
    if state["next_agent"] == "FINISH":
        return END
    return state["next_agent"]


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("research", research_node)
    graph.add_node("analysis", analysis_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {"research": "research", "analysis": "analysis", END: END},
    )
    graph.add_edge("research", "supervisor")
    graph.add_edge("analysis", "supervisor")

    return graph.compile()
