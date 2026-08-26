"""A single ReAct agent with all four tools available.

Uses LangGraph's prebuilt create_react_agent rather than hand-parsing a
Thought/Action/Observation text loop: llama3.2 supports native tool-calling, and
tool-calling is a strictly more reliable way to implement the same ReAct pattern than
parsing free-text "Action: tool_name(args)" out of a completion.
"""

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import create_react_agent

from src.agents.tools import calculator, fetch_url, rag_query, web_search
from src.config import settings

_TOOLS = [web_search, calculator, fetch_url, rag_query]


def run_react_agent(task: str) -> str:
    """Run one ReAct agent over a single task and return its final text answer."""
    llm = ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
    )
    agent = create_react_agent(llm, _TOOLS)

    # Each ReAct step is roughly two graph super-steps (agent turn -> tool turn); +1
    # leaves room for the final agent turn that answers without another tool call.
    recursion_limit = settings.max_react_steps * 2 + 1

    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content=task)]},
            config={"recursion_limit": recursion_limit},
        )
    except GraphRecursionError:
        return f"error: agent did not finish within {settings.max_react_steps} steps"

    return result["messages"][-1].content
