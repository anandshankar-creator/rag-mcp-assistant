# Model Context Protocol (MCP) & Multi-Agent Inventory

**Audit Standard:** Strict Codebase Verification of `D:\rag-mcp-assistant`  
**MCP Framework:** Anthropic Official Python SDK (`mcp>=1.0.0,<2.0.0`, `mcp.server.fastmcp.FastMCP`)  
**Total Verified MCP Servers:** 5  
**Total Verified FastMCP Tools:** 17  
**Multi-Agent Orchestrator:** LangGraph StateGraph (`agents/graph.py`)

---

## 1. Multi-Agent System Architecture

### 1.1 Nature of the Multi-Agent System
The system is implemented as a **compiled stateful Multi-Agent DAG workflow** coordinated by LangGraph (`agents/graph.py`). Rather than a single monolithic script or an unconstrained loop of autonomous LLM calls, the architecture enforces deterministic boundaries between specialized agent nodes. Each node processes a shared `AgentState` object and delegates work strictly within its domain:

| Agent / Component Node | Implementation File | Primary Role & Operational Boundary |
|---|---|---|
| **Context Loader** (`load_context`) | [`agents/graph.py`](file:///D:/rag-mcp-assistant/agents/graph.py#L75) | Fetches past conversational turns from SQLite `chat_history` and injects student profile preferences. |
| **Orchestrator Node** (`router_node`) | [`agents/orchestrator.py`](file:///D:/rag-mcp-assistant/agents/orchestrator.py) | Classifies incoming intent into `QA`, `ACTION`, `CHAINED`, or `CHAT` using few-shot classification and pattern detectors. |
| **Planner Node** (`planner_node`) | [`agents/planner.py`](file:///D:/rag-mcp-assistant/agents/planner.py) | Deconstructs multi-step goals into a structured JSON Step DAG. Enforces bounded execution ($\le 10$ steps). |
| **Executor Node** (`executor_node`) | [`agents/graph.py`](file:///D:/rag-mcp-assistant/agents/graph.py#L480) | Sequentially executes planned DAG steps, passing outputs from retrieval steps to action steps. Halts on missing data. |
| **RAG Agent Node** (`rag_node`) | [`agents/rag_agent.py`](file:///D:/rag-mcp-assistant/agents/rag_agent.py) | Executes dense semantic retrieval via ChromaDB, applies the $\tau = 0.30$ anti-hallucination gate, and triggers web fallback. |
| **Action Agent Node** (`action_node`) | [`agents/action_agent.py`](file:///D:/rag-mcp-assistant/agents/action_agent.py) | Dynamic broker for FastMCP tools. Validates parameters, executes tools, and constructs execution receipts. |
| **Chat Node** (`chat_node`) | [`agents/graph.py`](file:///D:/rag-mcp-assistant/agents/graph.py#L440) | Handles pure conversational chit-chat without invoking external tools or vector searches. |
| **Final Responder Node** (`responder_node`)| [`agents/graph.py`](file:///D:/rag-mcp-assistant/agents/graph.py#L800) | Formulates the final user-facing text, validates inline citations `[file, page]`, and logs the turn to SQLite. |

---

## 2. FastMCP Tool Microservices vs. Conventional Functions

In this architecture, tools are strictly separated from agent logic via the **Model Context Protocol (FastMCP)**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                          LangGraph Multi-Agent Engine                  │
│                                                                        │
│   [Orchestrator] ──► [Planner] ──► [Action Agent]                      │
└──────────────────────────────────────────┬─────────────────────────────┘
                                           │ MCP Protocol (JSON-RPC)
                                           ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  mcp_servers.client (MCPClientController)              │
│   Dynamic Discovery via FastMCP list_tools() & Signature Introspection │
└──────┬───────────────┬────────────────┬────────────────┬───────────────┘
       │               │                │                │               │
       ▼               ▼                ▼                ▼               ▼
┌─────────────┐ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ ┌─────────────┐
│ FastMCP     │ │ FastMCP     │  │ FastMCP     │  │ FastMCP     │ │ FastMCP     │
│ Reminder    │ │ Calendar    │  │ Email       │  │ PDF         │ │ Google      │
│ Server      │ │ Server      │  │ Server       │  │ Server      │ │ Workspace   │
└─────────────┘ └─────────────┘  └─────────────┘  └─────────────┘ └─────────────┘
```

- **Ordinary Python Function:** Tightly coupled in memory; requires explicit code changes, import adjustments, and prompt hardcoding to add or modify.
- **MCP Server:** Independent microservice instantiated via `mcp.server.fastmcp.FastMCP`. Discovers tools dynamically via `_tool_manager.list_tools()`.
- **MCP Tool:** A typed, schema-validated function registered with an `@mcp.tool()` decorator. Its input parameters, required fields, and docstring descriptions are parsed into JSON Schema definitions for LLM tool calling.

---

## 3. Verified MCP Servers & Tools Inventory Table

| Server Name | Transport | Tool Name | Purpose | Input Schema (Properties & Required) | Output Format | Implementation File | Test Evidence |
|---|---|---|---|---|---|---|---|
| `reminder_server` | In-process FastMCP | `create_reminder` | Schedules local notification & stores in SQLite | `title` (str, req), `due_datetime` (str, req), `note` (str) | Dict (`status`, `reminder_id`, `due_datetime`) | [`mcp_servers/reminder_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/reminder_server.py) | `tests/test_mcp_servers.py::test_reminder_mcp_lifecycle` |
| `reminder_server` | In-process FastMCP | `list_reminders` | Lists pending/completed reminders | `status_filter` (str, opt) | List of reminder records | [`mcp_servers/reminder_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/reminder_server.py) | `tests/test_mcp_servers.py::test_reminder_mcp_lifecycle` |
| `reminder_server` | In-process FastMCP | `delete_reminder` | Deletes reminder by ID | `reminder_id` (int, req) | Dict (`status`, `deleted_id`) | [`mcp_servers/reminder_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/reminder_server.py) | Verified in test suite |
| `calendar_server` | In-process FastMCP | `create_event` | Generates standard RFC 5545 `.ics` file | `title` (str, req), `start` (str, req), `end` (str), `attendees` (str), `description` (str) | Dict (`status`, `ics_path`, `event_id`) | [`mcp_servers/calendar_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/calendar_server.py) | `tests/test_mcp_servers.py::test_calendar_mcp_lifecycle` |
| `calendar_server` | In-process FastMCP | `list_events` | Queries scheduled `.ics` events | `date_range` (str, opt) | List of event dicts | [`mcp_servers/calendar_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/calendar_server.py) | `tests/test_mcp_servers.py::test_calendar_mcp_lifecycle` |
| `calendar_server` | In-process FastMCP | `delete_event` | Deletes calendar event & `.ics` file | `event_id` (int, req) | Dict (`status`, `deleted_id`) | [`mcp_servers/calendar_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/calendar_server.py) | Verified in test suite |
| `email_server` | In-process FastMCP | `preview_email` | Generates HITL email preview card | `to` (str, req), `subject` (str, req), `body` (str, req), `attachment_path` (str), `session_id` (str) | Dict (`status: preview`, `to`, `subject`, `preview_html`) | [`mcp_servers/email_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/email_server.py) | `tests/test_mcp_servers.py::test_email_mcp_hitl_and_send` |
| `email_server` | In-process FastMCP | `send_email` | Sends email via SMTP with HITL safety gate | `to` (str, req), `subject` (str, req), `body` (str, req), `attachment_path` (str), `confirmed` (bool, default False), `session_id` (str) | Dict (`status: success/requires_confirmation`, `message_id`) | [`mcp_servers/email_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/email_server.py) | `tests/test_email_regression.py` |
| `pdf_server` | In-process FastMCP | `generate_pdf` | Compiles academic PDF report via ReportLab | `title` (str, req), `content` (str, req), `filename` (str, req) | Dict (`status: success`, `pdf_path`, `sha256`, `size_bytes`) | [`mcp_servers/pdf_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/pdf_server.py) | `tests/test_pdf_download_regression.py` |
| `google_services_server` | In-process FastMCP | `google_calendar_create_event` | Creates verified event in Google Calendar API v3 | `title` (str, req), `start_time` (str, req), `end_time` (str), `description` (str), `attendees` (list) | Dict (`status: success`, `google_event_id`, `html_link`) | [`mcp_servers/google_services_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/google_services_server.py) | `tests/test_google_calendar_regression.py` |
| `google_services_server` | In-process FastMCP | `google_calendar_list_events` | Reads back verified events from Google Calendar | `max_results` (int), `date_range` (str) | Dict (`status: success`, `events`: list) | [`mcp_servers/google_services_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/google_services_server.py) | `tests/test_google_calendar_regression.py` |
| `google_services_server` | In-process FastMCP | `google_gmail_send_message` | Sends verified email via Gmail REST API v1 | `to` (str, req), `subject` (str, req), `body` (str, req), `confirmed` (bool), `attachment_path` (str) | Dict (`status: success`, `message_id`, `thread_id`) | [`mcp_servers/google_services_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/google_services_server.py) | `tests/test_email_regression.py` |
| `google_services_server` | In-process FastMCP | `google_gmail_list_messages` | Searches Gmail messages with query filters | `query` (str), `max_results` (int) | Dict (`status: success`, `messages`: list) | [`mcp_servers/google_services_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/google_services_server.py) | `tests/test_google_services_mcp.py` |
| `google_services_server` | In-process FastMCP | `google_tasks_create` | Creates task in Google Tasks API v1 | `title` (str, req), `notes` (str), `due` (str) | Dict (`status: success`, `task_id`) | [`mcp_servers/google_services_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/google_services_server.py) | `tests/test_google_services_mcp.py` |
| `google_services_server` | In-process FastMCP | `google_tasks_list` | Lists tasks from Google Tasks API v1 | `max_results` (int) | Dict (`status: success`, `tasks`: list) | [`mcp_servers/google_services_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/google_services_server.py) | `tests/test_google_services_mcp.py` |
| `google_services_server` | In-process FastMCP | `google_drive_search` | Searches files in Google Drive API v3 | `query` (str), `page_size` (int) | Dict (`status: success`, `files`: list) | [`mcp_servers/google_services_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/google_services_server.py) | `tests/test_google_services_mcp.py` |
| `google_services_server` | In-process FastMCP | `google_keep_note` | Captures quick note stub | `title` (str, req), `text` (str, req) | Dict (`status: success`, `note_id`) | [`mcp_servers/google_services_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/google_services_server.py) | `tests/test_google_services_mcp.py` |

---

## 4. Discovery, Calling, and Validation Mechanics

### 4.1 Tool Discovery
In [`mcp_servers/client.py`](file:///D:/rag-mcp-assistant/mcp_servers/client.py#L49), `MCPClientController.discover_tools()` iterates over `DEFAULT_SERVERS`, imports each server module, and accesses `mcp_instance._tool_manager.list_tools()`. It cleans docstrings, extracts parameter JSON schemas, and stores callable function references in `_function_registry`.

### 4.2 Dynamic Argument Validation
When an agent node invokes `execute_tool(tool_name, arguments)`:
1. Validates that `tool_name` exists in `_tools_cache`.
2. Inspects the target function signature via `inspect.signature(fn)`.
3. Checks for required parameters. If a required argument is missing, returns a structured error without crashing:
   `{"status": "error", "message": "Missing required parameter 'param_name' for tool 'tool_name'."}`.
4. Executes the tool inside a `try...except` block, capturing uncaught exceptions and returning an honest diagnostic receipt.

### 4.3 Security Boundaries & Permission Controls
- **Human-in-the-Loop Safety Gate:** The `send_email` and `google_gmail_send_message` tools strictly enforce `if not confirmed: return {"status": "requires_confirmation", ...}`. Unconfirmed calls halt execution and present a confirmation card to the user.
- **Path Traversal Sanitization:** The `generate_pdf` tool strips directory traversal components (`../`, absolute paths) from requested filenames, confining output strictly to `outputs/`.
- **Diagnostic Transparency:** When Google OAuth credentials (`credentials/credentials.json`) are absent, `google_services_server` tools return `status: "unconfigured"` with honest troubleshooting guidance rather than failing silently.
