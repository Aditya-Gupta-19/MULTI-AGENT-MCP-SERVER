"""Agent tools: web_search, calculator, fetch_url, rag_query.

Every tool returns a string (never raises) — a ReAct loop treats a raised exception as
an unrecoverable crash, but an error string is just another Observation the agent can
reason about and route around.
"""

import html
import ipaddress
import json
import math
import re
import time
from urllib.parse import urlparse

import httpx
from duckduckgo_search import DDGS
from langchain_core.tools import tool

from src.config import settings

_SEARCH_THROTTLE_SECONDS = 1  # DDGS rate-limits fast repeated calls

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # includes the 169.254.169.254 cloud metadata IP
]

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")

_MAX_FETCH_CHARS = 5000


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the public web via DuckDuckGo. Returns a JSON array of
    {title, href, body} results, or a JSON object with an "error" key on failure."""
    time.sleep(_SEARCH_THROTTLE_SECONDS)
    try:
        results = DDGS().text(query, max_results=max_results)
    except Exception as exc:  # DDGS can raise on rate limits, timeouts, network errors
        return json.dumps({"error": f"web_search failed: {exc}"})
    return json.dumps(results)


@tool
def calculator(expression: str) -> str:
    """Evaluate a math expression. Only math.* functions and arithmetic operators are
    reachable — every other builtin is stripped. Returns the numeric result as a
    string, or "error: ..." on failure."""
    try:
        result = eval(expression, {"__builtins__": {}}, {"math": math})
    except Exception as exc:
        return f"error: {exc}"
    return str(result)


def _is_blocked_host(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # Not a literal IP — a hostname that *resolves* to a private/loopback address
        # (DNS rebinding) is not caught here. Closed in Stage 11 by checking the
        # resolved IP instead of the literal string.
        return False
    return any(ip in network for network in _BLOCKED_NETWORKS)


def _html_to_text(markup: str) -> str:
    text = _SCRIPT_STYLE_RE.sub(" ", markup)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return " ".join(text.split())


@tool
def fetch_url(url: str) -> str:
    """Fetch a public HTTP(S) URL and return cleaned page text (script/style stripped,
    tags removed, whitespace collapsed, truncated to 5000 chars). Refuses localhost,
    private, and link-local addresses (including the cloud metadata IP) as an SSRF
    guard. Does not follow redirects, so the guard can't be bypassed by a public URL
    that redirects to an internal one."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "error: URL blocked for security reasons (scheme must be http or https)"
    if not parsed.hostname or _is_blocked_host(parsed.hostname):
        return "error: URL blocked for security reasons (private or local address)"

    try:
        response = httpx.get(url, timeout=10.0, follow_redirects=False)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return f"error: failed to fetch URL: {exc}"

    return _html_to_text(response.text)[:_MAX_FETCH_CHARS]


@tool
def rag_query(question: str) -> str:
    """Ask the external RAG project's /query endpoint a question and return its JSON
    response. That service is a separate project and must be running independently
    (see settings.rag_api_base_url) — this tool fails gracefully, not with a crash,
    if it's unreachable."""
    try:
        response = httpx.post(
            f"{settings.rag_api_base_url}/query",
            json={"question": question},
            headers={"X-API-Key": settings.rag_api_key},
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return f"error: RAG service unavailable: {exc}"
    return json.dumps(response.json())
