import itertools

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from src.agents import react_agent


class _FakeToolCallingChatModel(GenericFakeChatModel):
    """GenericFakeChatModel plus a bind_tools that just returns self — the base class
    raises NotImplementedError, but create_react_agent calls bind_tools() up front."""

    def bind_tools(self, tools, **kwargs):
        return self


def _model_returning(*messages):
    return lambda **kwargs: _FakeToolCallingChatModel(messages=iter(messages))


def _model_looping_forever():
    call = AIMessage(
        content="",
        tool_calls=[{"name": "calculator", "args": {"expression": "1+1"}, "id": "call_1"}],
    )
    # itertools.repeat, not a finite list: the recursion-limit test needs the fake
    # model to keep answering with a tool call no matter how many turns occur before
    # GraphRecursionError trips.
    return lambda **kwargs: _FakeToolCallingChatModel(messages=itertools.repeat(call))


def test_run_react_agent_returns_final_message_content(monkeypatch):
    monkeypatch.setattr(
        react_agent, "ChatOllama", _model_returning(AIMessage(content="mocked final answer"))
    )

    result = react_agent.run_react_agent("What is 2+2?")

    assert result == "mocked final answer"


def test_run_react_agent_returns_graceful_error_on_recursion_limit(monkeypatch):
    monkeypatch.setattr(react_agent, "ChatOllama", _model_looping_forever())
    monkeypatch.setattr(react_agent.settings, "max_react_steps", 1)

    result = react_agent.run_react_agent("loop forever")

    assert result.startswith("error:")


@pytest.mark.integration
def test_run_react_agent_live_ollama():
    """Requires a running Ollama with llama3.2 pulled — the exact smoke command from
    claude.md's Daily Development Commands, plus a tool-use case."""
    result = react_agent.run_react_agent("What is 12 times 8? Use the calculator tool.")
    assert "96" in result
