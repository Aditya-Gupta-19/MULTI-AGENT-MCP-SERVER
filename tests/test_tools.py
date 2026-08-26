import json

import httpx
import pytest

from src.agents import tools


# --- web_search ---------------------------------------------------------------


def test_web_search_returns_json_array(monkeypatch):
    monkeypatch.setattr(tools.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        tools.DDGS,
        "text",
        lambda self, keywords, max_results=None: [
            {"title": "Result A", "href": "https://example.com/a", "body": "snippet a"}
        ],
    )

    result = json.loads(tools.web_search.func("test query"))

    assert result == [{"title": "Result A", "href": "https://example.com/a", "body": "snippet a"}]


def test_web_search_failure_returns_error_json_not_a_crash(monkeypatch):
    monkeypatch.setattr(tools.time, "sleep", lambda _seconds: None)

    def _raise(self, keywords, max_results=None):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(tools.DDGS, "text", _raise)

    result = json.loads(tools.web_search.func("test query"))

    assert "error" in result


# --- calculator ----------------------------------------------------------------


def test_calculator_arithmetic():
    assert tools.calculator.func("2 + 2") == "4"


def test_calculator_math_functions():
    assert tools.calculator.func("math.sqrt(16)") == "4.0"


def test_calculator_undefined_name_returns_error_string():
    result = tools.calculator.func("os.system('echo hi')")
    assert result.startswith("error:")


def test_calculator_syntax_error_returns_error_string():
    result = tools.calculator.func("2 +")
    assert result.startswith("error:")


def test_calculator_sandbox_gap_not_yet_hardened():
    """Documents a known, deliberately-deferred gap rather than hiding it: an empty
    __builtins__ blocks *name* lookups (os, __import__, ...) but not attribute-chain
    introspection starting from a literal — `()` needs no name to reach its own type
    and walk to every loaded class. This test only proves introspection succeeds
    (harmless on its own); it never instantiates or calls anything. Stage 11 closes
    this with a regex pre-filter that only allows digits/operators/math.* tokens.
    Flip this to assertRaises once that lands."""
    result = tools.calculator.func("().__class__.__bases__[0].__subclasses__().__len__()")
    assert result.isdigit()


# --- fetch_url -------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://10.1.2.3/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
    ],
)
def test_fetch_url_blocks_private_and_local_addresses(url):
    result = tools.fetch_url.func(url)
    assert result.startswith("error: URL blocked")


def test_fetch_url_blocks_non_http_scheme():
    result = tools.fetch_url.func("ftp://example.com/file")
    assert result.startswith("error: URL blocked")


def test_fetch_url_strips_tags_and_scripts(monkeypatch):
    html_body = "<html><head><style>body{color:red}</style></head><body><script>evil()</script><p>Hello &amp; welcome</p></body></html>"

    def _fake_get(url, timeout=None, follow_redirects=None):
        return httpx.Response(200, text=html_body, request=httpx.Request("GET", url))

    monkeypatch.setattr(tools.httpx, "get", _fake_get)

    result = tools.fetch_url.func("https://example.com/page")

    assert result == "Hello & welcome"


def test_fetch_url_reports_http_errors_gracefully(monkeypatch):
    def _fake_get(url, timeout=None, follow_redirects=None):
        return httpx.Response(500, text="boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(tools.httpx, "get", _fake_get)

    result = tools.fetch_url.func("https://example.com/page")

    assert result.startswith("error: failed to fetch URL")


# --- rag_query -------------------------------------------------------------------


def test_rag_query_returns_json_response(monkeypatch):
    def _fake_post(url, json=None, headers=None, timeout=None):
        return httpx.Response(
            200, json={"answer": "42"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(tools.httpx, "post", _fake_post)

    result = json.loads(tools.rag_query.func("What is the answer?"))

    assert result == {"answer": "42"}


def test_rag_query_unreachable_service_returns_error_not_a_crash(monkeypatch):
    def _fake_post(url, json=None, headers=None, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(tools.httpx, "post", _fake_post)

    result = tools.rag_query.func("What is the answer?")

    assert result.startswith("error: RAG service unavailable")
