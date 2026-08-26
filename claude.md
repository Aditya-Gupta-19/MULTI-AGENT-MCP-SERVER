CLAUDE.md — Project 2: Multi-Agent + MCP Server

> Drop this file at the root of `production-agents/`. Claude Code reads it automatically on every session.

---

Project Overview
What this is: A production-grade Multi-Agent AI system with an MCP (Model Context Protocol) server. A supervisor agent orchestrates specialized sub-agents (research, analysis) using LangGraph. An MCP server exposes tools to Claude Desktop. All free, all local.
Stack (all free, all local):
Orchestration: LangGraph (StateGraph, TypedDict state machine)
LLM: Ollama + Llama3.2 (local, $0/call)
Web Search: DuckDuckGo (`duckduckgo-search`, no API key)
MCP Server: FastMCP (mcp package v1.1.0)
Observability: Arize Phoenix (LLM traces, localhost:6006)
API: FastAPI wrapper for external access
Pattern: Supervisor → Research Agent + Analysis Agent (ReAct loop)

---

Project Structure

```
production-agents/
├── src/
│   ├── config.py                  # Pydantic Settings — all config from .env
│   ├── agents/
│   │   ├── tools.py               # DuckDuckGo search, calculator, fetch_url
│   │   ├── react_agent.py         # Single ReAct agent (Thought→Action→Observation)
│   │   └── graph.py               # LangGraph multi-agent state machine
│   ├── mcp_server/
│   │   └── server.py              # FastMCP server (Claude Desktop integration)
│   ├── api/
│   │   └── main.py                # FastAPI wrapper for agent access
│   └── observability/
│       └── tracing.py             # Arize Phoenix setup
├── tests/
│   ├── test_tools.py              # Unit tests for each tool
│   ├── test_graph.py              # LangGraph pipeline tests
│   └── test_mcp.py                # MCP server tests
├── data/
│   └── agent_logs/                # Agent run logs (gitignored)
├── .env                           # Local secrets (NEVER commit)
├── .env.example                   # Template for teammates
└── requirements.txt
```

---

Environment Setup (Run Once)

```bash
# 1. Install Ollama + pull model
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.2

# 2. Python environment
python -m venv venv && source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy env file
cp .env.example .env
# Edit .env — set your API_KEY
```

requirements.txt:

```
langgraph==0.2.35
langchain==0.3.3
langchain-community==0.3.3
langchain-ollama==0.2.0
duckduckgo-search==6.3.2
mcp==1.1.0
fastmcp==2.0.0
fastapi==0.115.0
uvicorn==0.30.6
httpx==0.27.0
arize-phoenix==4.29.0
pydantic-settings==2.5.2
pytest==8.3.3
```

---

Daily Development Commands

```bash
# Activate environment (every session)
source venv/bin/activate

# Start Ollama
ollama serve &

# Run FastAPI server
uvicorn src.api.main:app --reload --port 8001
# → http://localhost:8001/docs

# Start Phoenix observability
python -m phoenix.server.main
# → http://localhost:6006

# Test single ReAct agent
python -c "from src.agents.react_agent import run_react_agent; print(run_react_agent('What is 2+2?'))"

# Test multi-agent graph
python -c "from src.agents.graph import build_graph; g=build_graph(); print(g.invoke({'messages':[], 'next_agent':'supervisor', 'final_answer':'', 'iteration':0, 'task':'What is the capital of France?'}))"

# Run MCP server (stdio for Claude Desktop)
python -m src.mcp_server.server
```

---

Testing Commands

```bash
# Unit tests
pytest tests/ -v

# Single tool test
pytest tests/test_tools.py -v

# Graph pipeline test
pytest tests/test_graph.py -v

# Health check
curl http://localhost:8001/health

# Run agent via API
curl -X POST http://localhost:8001/run \
  -H "X-API-Key: dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"task": "Search for the latest news about AI agents"}'
```

---

Claude Desktop MCP Config
Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "production-ai-tools": {
      "command": "/absolute/path/to/production-agents/venv/bin/python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "/absolute/path/to/production-agents"
    }
  }
}
```

Windows path: `%APPDATA%\Claude\claude_desktop_config.json`
After saving, restart Claude Desktop. Tools appear in the Claude Desktop tool picker.

---

Key Design Decisions (Do Not Change Without Understanding Why)
Decision Why
`TypedDict` for AgentState LangGraph requires typed state. `Annotated[list, operator.add]` on messages = append-only. Never overwrite.
Max iteration guard (default 10) Without it, agents loop forever. Guard at supervisor level: `if iteration >= max → FINISH`.
DuckDuckGo (no API key) Google Search API = $5/1000 queries. DDGS is free, reliable, and needs zero setup.
`format="json"` on supervisor LLM Forces structured routing output. Parse with `json.loads()`, never regex.
URL blocklist in `fetch_url` Blocks 127.x, 192.168.x, 10.x, metadata endpoints. Prevents SSRF attacks from LLM-injected URLs.
`eval()` with empty `__builtins__` Safe calculator: allows only `math.*` functions. `{"__builtins__": {}}` removes all dangerous builtins.
`task_acks_late=True` in Celery Not used here but good default: tasks re-queue if worker dies mid-run.
MCP uses stdio transport Claude Desktop uses stdio by default. No networking needed — process-to-process via stdin/stdout.
FastMCP over raw MCP SDK FastMCP is the FastAPI of MCP — decorators instead of boilerplate. Same wire protocol underneath.
Supervisor returns `FINISH` not `END` LangGraph conditional edge maps string → node. `FINISH` maps to `END` constant. Never compare to `END` directly in the router.

---

Agent Flow (The Core)

```
User Task
    │
    ▼
Supervisor Node
    │  Reads task + message history
    │  Outputs JSON: {"next": "research"|"analysis"|"FINISH", "answer": "..."}
    │
    ├──→ Research Node
    │       │  Runs ReAct loop: web_search, fetch_url tools
    │       │  Appends AIMessage with findings
    │       └──→ back to Supervisor
    │
    ├──→ Analysis Node
    │       │  Runs ReAct loop: calculator, fetch_url tools
    │       │  Appends AIMessage with analysis
    │       └──→ back to Supervisor
    │
    └──→ FINISH
            │  Returns final_answer from state
            ▼
         User sees answer
```

---

AgentState Reference

```python
class AgentState(TypedDict):
    messages: Annotated[list, operator.add]   # ALL messages — append only
    next_agent: str                            # "research" | "analysis" | "FINISH"
    final_answer: str                          # Set by supervisor when done
    iteration: int                             # Guard: increment each supervisor call
    task: str                                  # Original user task — never changes
```

---

MCP Tools Exposed
Tool Description
`web_search(query, max_results)` DuckDuckGo web search, returns JSON array
`calculator(expression)` Safe math eval using only `math.*` functions
`fetch_url(url)` HTTP GET with SSRF blocklist, returns cleaned text
`rag_query(question)` Queries Project 1 RAG system at localhost:8000

---

Configuration Reference (.env variables)

```env
# LLM
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.2
LLM_TEMPERATURE=0.0

# Agent behavior
MAX_AGENT_ITERATIONS=10
MAX_REACT_STEPS=5

# API
API_KEY=your-secret-key-here
RATE_LIMIT_PER_MINUTE=60

# Observability
LOG_LEVEL=INFO
PHOENIX_PORT=6006
```

---

Common Issues & Fixes

```
Issue: "ChatOllama not found" or import error
Fix:   pip install langchain-ollama langchain-community

Issue: Supervisor outputs invalid JSON
Fix:   Add format="json" to ChatOllama call.
       Also add JSON example to supervisor prompt.

Issue: LangGraph "recursion limit" error
Fix:   This is the max_iterations guard. Increase MAX_AGENT_ITERATIONS in .env.
       Or check if supervisor is not outputting FINISH correctly.

Issue: DuckDuckGo rate limit / empty results
Fix:   Add time.sleep(1) between calls.
       DDGS is free but throttles fast loops.

Issue: MCP server not appearing in Claude Desktop
Fix:   1. Check absolute paths in claude_desktop_config.json
       2. Restart Claude Desktop (not just reload)
       3. Run: python -m src.mcp_server.server — must start without errors
       4. Check Console.app (macOS) for MCP connection errors

Issue: "ModuleNotFoundError: No module named 'mcp'"
Fix:   pip install mcp fastmcp

Issue: fetch_url blocked "URL blocked for security reasons"
Fix:   You tried to fetch localhost/192.168.x/10.x — this is intentional SSRF protection.
       Only fetch public internet URLs.

Issue: Agent loops without finishing
Fix:   Check supervisor prompt — add explicit FINISH condition.
       Check MAX_AGENT_ITERATIONS — must be set in .env and loaded in config.py.
```

---

Phases Completed
[x] Phase 1: Environment Setup (Ollama, venv, requirements.txt)
[x] Phase 2: Configuration (Pydantic Settings, .env)
[x] Phase 3: Agent Tools (DuckDuckGo, calculator, fetch_url)
[x] Phase 4: Single ReAct Agent (Thought → Action → Observation loop)
[x] Phase 5: LangGraph Multi-Agent (Supervisor + Research + Analysis nodes)
[x] Phase 6: FastAPI Wrapper (agent endpoint, auth, rate limiting)
[x] Phase 7: MCP Server (FastMCP, Claude Desktop integration)
[x] Phase 8: Observability + Tests (Arize Phoenix, pytest)

---

Production Layer Coverage
Layer Implementation
Orchestration LangGraph StateGraph, supervisor pattern, conditional routing
Safety Max iteration guard, URL SSRF blocklist, safe calculator eval
Observability Arize Phoenix traces every agent call (model, tokens, latency)
Security X-API-Key auth, rate limiting, no API keys in code (.env only)
MCP Integration FastMCP server with 4 tools, stdio transport, Claude Desktop ready
Testing pytest unit tests for all tools and graph pipeline

---

This CLAUDE.md is for use with Claude Code. Drop it at the project root and Claude Code will read it automatically at session start.
