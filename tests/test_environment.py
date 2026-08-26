"""Stage 1 smoke test: every core dependency must import cleanly before later stages build on it."""


def test_core_dependencies_import():
    import duckduckgo_search  # noqa: F401
    import fastapi  # noqa: F401
    import fastmcp  # noqa: F401
    import httpx  # noqa: F401
    import langchain  # noqa: F401
    import langchain_community  # noqa: F401
    import langchain_ollama  # noqa: F401
    import langgraph  # noqa: F401
    import mcp  # noqa: F401
    import phoenix  # noqa: F401
    import pydantic_settings  # noqa: F401
    import uvicorn  # noqa: F401


def test_observability_instrumentation_imports():
    import openinference.instrumentation.langchain  # noqa: F401
    import opentelemetry.exporter.otlp.proto.grpc  # noqa: F401
