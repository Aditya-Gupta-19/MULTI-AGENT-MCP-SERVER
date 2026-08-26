import operator

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END

from src.agents import graph as graph_module
from src.agents.graph import AgentState, build_graph, route_supervisor


def _base_state(**overrides) -> AgentState:
    state = {
        "messages": [],
        "next_agent": "",
        "final_answer": "",
        "iteration": 0,
        "task": "What is 2 + 2?",
    }
    state.update(overrides)
    return state


class _StubLLM:
    def __init__(self, content: str):
        self._content = content

    def invoke(self, messages):
        return type("Response", (), {"content": self._content})()


# --- route_supervisor: the only place "FINISH" is translated to END --------------


def test_route_supervisor_finish_maps_to_end():
    assert route_supervisor(_base_state(next_agent="FINISH")) is END


def test_route_supervisor_research_routes_to_research_node():
    assert route_supervisor(_base_state(next_agent="research")) == "research"


def test_route_supervisor_analysis_routes_to_analysis_node():
    assert route_supervisor(_base_state(next_agent="analysis")) == "analysis"


# --- supervisor_node: iteration guard -----------------------------------------------


def test_supervisor_node_forces_finish_at_max_iterations(monkeypatch):
    monkeypatch.setattr(graph_module.settings, "max_agent_iterations", 3)
    state = _base_state(iteration=2, messages=[AIMessage(content="prior finding")])

    result = graph_module.supervisor_node(state)

    assert result["next_agent"] == "FINISH"
    assert result["iteration"] == 3
    assert "prior finding" in result["final_answer"]


# --- supervisor_node: JSON routing decisions ----------------------------------------


def test_supervisor_node_parses_valid_json_decision(monkeypatch):
    monkeypatch.setattr(graph_module.settings, "max_agent_iterations", 10)
    monkeypatch.setattr(
        graph_module, "_llm", lambda **kwargs: _StubLLM('{"next": "research", "answer": ""}')
    )

    result = graph_module.supervisor_node(_base_state())

    assert result["next_agent"] == "research"
    assert result["iteration"] == 1


def test_supervisor_node_invalid_json_forces_finish(monkeypatch):
    monkeypatch.setattr(graph_module.settings, "max_agent_iterations", 10)
    monkeypatch.setattr(graph_module, "_llm", lambda **kwargs: _StubLLM("not json at all"))

    result = graph_module.supervisor_node(_base_state())

    assert result["next_agent"] == "FINISH"
    assert "invalid JSON" in result["final_answer"]


def test_supervisor_node_unknown_route_forces_finish(monkeypatch):
    monkeypatch.setattr(graph_module.settings, "max_agent_iterations", 10)
    monkeypatch.setattr(
        graph_module,
        "_llm",
        lambda **kwargs: _StubLLM('{"next": "not_a_real_agent", "answer": ""}'),
    )

    result = graph_module.supervisor_node(_base_state())

    assert result["next_agent"] == "FINISH"


# --- sub-agent nodes: findings get appended, never overwrite -----------------------


def test_research_node_appends_a_finding_message(monkeypatch):
    def _fake_create_react_agent(llm, tools):
        class _FakeCompiledGraph:
            def invoke(self, input_, config=None):
                return {"messages": input_["messages"] + [AIMessage(content="found it")]}

        return _FakeCompiledGraph()

    monkeypatch.setattr(graph_module, "create_react_agent", _fake_create_react_agent)

    state = _base_state(messages=[AIMessage(content="earlier message")])
    result = graph_module.research_node(state)

    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "[research] found it"


def test_agent_state_messages_field_uses_operator_add_reducer():
    """Confirms the reducer is actually wired on the TypedDict annotation, not just
    described in a docstring."""
    annotation = AgentState.__annotations__["messages"]
    assert annotation.__metadata__[0] is operator.add


# --- full graph, live Ollama --------------------------------------------------------


@pytest.mark.integration
def test_build_graph_live_ollama_end_to_end():
    """The exact smoke invocation from claude.md's Daily Development Commands."""
    g = build_graph()
    result = g.invoke(
        {
            "messages": [],
            "next_agent": "supervisor",
            "final_answer": "",
            "iteration": 0,
            "task": "What is the capital of France?",
        }
    )
    assert "paris" in result["final_answer"].lower()
