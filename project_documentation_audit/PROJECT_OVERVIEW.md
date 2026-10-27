# Project Overview: RAG-Based Multi-Agent Personal Assistant Using MCP

**Document Status:** Complete & Verified Technical Audit  
**Project Path:** `D:\rag-mcp-assistant`  
**Host Environment:** Windows 10/11, Python 3.11.1  
**Affiliated Institution:** APJ Abdul Kalam Technological University (KTU) | S7 B.Tech Computer Science & Engineering

---

## 1. Project Identity and Summary

- **Exact Project Title:**  
  *A Retrieval-Augmented Generation Based Multi-Agent Personal Assistant Architecture Using the Model Context Protocol (MCP)*
- **Academic Course Specification:**  
  CS451 / CS402 Final Year B.Tech Project Phase 1 (Academic Year 2025–2026).
- **Core Technology Paradigm:**  
  Decoupled Multi-Agent State Machine (LangGraph), Dense Local Semantic Retrieval (ChromaDB + `sentence-transformers`), Anti-Hallucination Cosine Gating ($\tau = 0.30$), Domain-Ranked Web Fallback (DuckDuckGo), Open Tool Microservices (Anthropic FastMCP), and Multi-Provider LLM Integration (Google Gemini with Thread-Safe Key Rotation).

---

## 2. Problem Statement & Motivation

### 2.1 The Two Fundamental Deficiencies in Modern LLM Assistants
Modern conversational assistants (such as default ChatGPT, Claude, or mobile voice assistants) suffer from two structural architectural flaws when deployed in academic or personal productivity environments:

1. **Parametric Hallucination on Private & Dynamic Data:**  
   Closed-book LLMs rely purely on pre-trained parametric weights. When queried on private course notes, unpublished syllabi, internal timetable revisions, or personal academic schedules, they cannot access local files. Consequently, they either invent plausible-sounding examination dates and syllabus regulations (hallucinations) or issue unhelpful generic apologies.
2. **Execution Isolation (Text Silos):**  
   Standard conversational interfaces operate as passive text generators. They lack deterministic, bi-directional interfaces to the underlying operating system or enterprise services. They cannot schedule real operating system reminders, generate standard RFC 5545 calendar files, compose and send authentic emails, or compile structured PDF reports without fragile, vendor-locked scripting.

### 2.2 Motivation
Undergraduate engineering students, researchers, and knowledge workers manage heterogeneous, fast-changing documents (lecture slides, PDF reports, exam schedules, course codes) alongside daily operational obligations (assignment deadlines, project synchronizations, email submissions). An effective personal assistant must:
- Ground every factual claim strictly in private local documents.
- Fall back intelligently to trusted authoritative web sources when local knowledge is insufficient.
- Execute real-world tools deterministically without compromising host system security.
- Decouple tool definitions so new capabilities can be plugged in without modifying core agent state graphs.

---

## 3. Proposed Solution vs. Conventional Chatbots

| Dimension | Conventional Chatbot (e.g. Pure ChatGPT) | Proposed RAG-MCP Multi-Agent Assistant |
|---|---|---|
| **Private Knowledge Handling** | Parametric guessing; frequent severe hallucinations on local documents | Dense semantic retrieval via ChromaDB; strict refusal gate if cosine similarity $< 0.30$ |
| **Citation Attribution** | Unverifiable claims or fabricated URLs | Verifiable inline citations: `[filename, page]` for local docs; live URLs for web sources |
| **Web Fallback Policy** | Blind browsing or disabled; prone to spam blogs | Two-stage trust ranking: checks local documents first, verifies chunk relevance, then queries Tier 1/2 domains |
| **Tool Execution Architecture** | Monolithic, hardcoded function calling locked inside prompt schemas | Anthropic's open Model Context Protocol (FastMCP): tools operate as independent client-server microservices |
| **Safety & Side-Effect Control**| Unguarded autonomous tool execution | Human-in-the-Loop (HITL) confirmation modal for impactful actions (email dispatch) |
| **LLM Provider Availability** | Single-vendor lock-in; fails on HTTP 429 quota exhaustion | Multi-provider abstraction with thread-safe `GeminiKeyManager` pool rotation and backoff |
| **Administrative Access** | Publicly accessible or third-party auth | Strict single-administrator auth: salted bcrypt (`rounds=12`), brute-force lockout, single-use reset tokens |

---

## 4. Main Objectives & Measurable Goals

1. **Deterministic Document Grounding:**  
   Achieve zero hallucinations on out-of-domain private queries through an anti-hallucination cosine similarity gate ($\tau = 0.30$).
2. **Universal Document-First Workflow:**  
   Enforce a mandatory 4-step workflow: local document search first $\rightarrow$ trusted web search second $\rightarrow$ combined hybrid evidence $\rightarrow$ honest uncertainty refusal.
3. **Decoupled Tool Orchestration via FastMCP:**  
   Implement 17 distinct tools across 5 independent FastMCP servers discovered dynamically at runtime without hardcoded schemas.
4. **Authenticated External Automations:**  
   Integrate real Google Calendar API v3 and Gmail API v1 with duplicate prevention, `Asia/Kolkata` (+05:30) timezone handling, and action introspection.
5. **Report-Grade Document Synthesis:**  
   Generate downloadable, publication-quality PDF reports using ReportLab with SHA-256 signature verification and secure authenticated download gates.
6. **Thread-Safe LLM Quota Failover:**  
   Support multiple Gemini API keys in a rotating key pool with 60-second backoff cooldown on HTTP 429 ResourceExhausted errors.
7. **Comprehensive System Verification:**  
   Maintain 100% pass rate across all 124 formal automated tests in `pytest`.

---

## 5. Scope & Current Boundaries

### In Scope (Implemented and Verified)
- Local document parsing and chunking for `.pdf`, `.docx`, `.txt`, and `.md` files.
- Dense embedding generation using `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions).
- Local persistent vector storage in ChromaDB (`student_knowledge_base`).
- LangGraph compiled state machine with 8 distinct nodes (`load_context`, `router_node`, `rag_node`, `action_node`, `chat_node`, `planner_node`, `executor_node`, `responder_node`).
- 5 FastMCP servers: `reminder_server`, `calendar_server`, `email_server`, `pdf_server`, `google_services_server`.
- Human-in-the-Loop confirmation workflow for email dispatch.
- DuckDuckGo web research with domain trust ranking (Tier 1 .edu/.gov, Tier 2 mainstream tech).
- Multi-key rotation pool for Google Gemini API with masked key logging.
- Single-administrator authentication portal with bcrypt hashing, brute-force protection, JWT sessions, and single-use password reset tokens.
- Interactive Streamlit web interface with compact sidebar, telemetry drawer, and in-chat PDF download.

### Out of Scope / Boundaries (Phase 2 & Deployment Considerations)
- Multi-user public registration (by design: single administrator personal assistant).
- Interactive Desktop OAuth consent on headless cloud containers (requires pre-generated tokens or local desktop execution).
- Distributed multi-node vector database clusters (local ChromaDB SQLite is used for lightweight self-containment).

---

## 6. Project Directory Tree & Component Responsibilities

```
D:\rag-mcp-assistant\
├── agents/                         # LangGraph Multi-Agent Architecture
│   ├── __init__.py                 # Agent package initialization
│   ├── action_agent.py             # FastMCP tool execution node & telemetry
│   ├── graph.py                    # Compiled LangGraph StateGraph & run_assistant entry point
│   ├── memory.py                   # SQLite chat history & student preferences manager
│   ├── orchestrator.py             # Intent classification node (QA, ACTION, CHAINED, CHAT)
│   ├── planner.py                  # Step DAG decomposition node (max 10 bounded steps)
│   └── rag_agent.py                # RAG retrieval node & similarity threshold gate
├── app/                            # Application Layer & API Gateway
│   ├── __init__.py                 # App package initialization
│   ├── auth.py                     # Administrator bcrypt auth, JWT sessions, brute-force defense
│   ├── auth_email.py               # Dedicated password-reset emailer (Gmail API / SMTP fallback)
│   ├── config.py                   # Settings loader (os.getenv with st.secrets fallback)
│   ├── main.py                     # FastAPI application entry point, CORS, startup hooks
│   └── routes.py                   # Protected REST API endpoints (/api/chat, /api/upload, etc.)
├── audit/                          # Playwright UI Verification Artifacts & Test Evidence
│   ├── screenshots/                # 11 Playwright capture PNGs (01_initial_ui_load to 11_dashboard)
│   ├── downloads/                  # Test generated PDF downloads
│   ├── verify_auth_flow.py         # End-to-end Playwright authentication verification script
│   ├── verify_live_ui.py           # Playwright UI verification script
│   └── [test_results.json]         # Raw JSON audit telemetry records
├── credentials/                    # Local OAuth Secrets & Tokens (Git-Ignored)
│   ├── credentials.json            # Google Cloud OAuth 2.0 desktop client credentials
│   └── google_token.json           # Cached Google OAuth access and refresh tokens
├── data/                           # Ingested Knowledge Base Repository
│   └── documents/                  # Reference documents (PDF, TXT, MD)
├── db/                             # Persistent Storage (Git-Ignored)
│   ├── assistant.db                # SQLite database (10 tables for memory, tools, and auth)
│   └── chroma/                     # ChromaDB persistent collection files
├── evaluation/                     # Automated Empirical Evaluation Framework
│   ├── report.py                   # Matplotlib chart generator & academic evaluation report
│   ├── run_eval.py                 # Empirical benchmark runner (QA & Action evaluation)
│   ├── testset.json                # Standardized test set (25 QA items, 6 Action items)
│   └── results/                    # Generated benchmark CSVs, JSONs, and PNG charts
├── llm/                            # Multi-Provider LLM Abstraction Layer
│   ├── base.py                     # Abstract LLMClient base class & LLMResponse containers
│   ├── claude_client.py            # Anthropic Claude SDK client implementation
│   ├── gemini_client.py            # Gemini client with thread-safe GeminiKeyManager rotation
│   └── ollama_client.py            # Local Ollama client for 100% offline LLMs
├── mcp_servers/                    # FastMCP Microservice Tool Servers
│   ├── calendar_server.py          # FastMCP server for RFC 5545 .ics calendar generation
│   ├── client.py                   # Dynamic FastMCP discovery controller & dispatch table
│   ├── db.py                       # SQLite connection factory & tool tables initialization
│   ├── email_server.py             # FastMCP server for HITL email preview & SMTP dispatch
│   ├── google_auth.py              # Google OAuth 2.0 desktop authentication flow
│   ├── google_services_server.py   # FastMCP server for Google Calendar, Gmail, Tasks & Drive
│   ├── pdf_server.py               # FastMCP server for ReportLab structured PDF synthesis
│   └── reminder_server.py          # FastMCP server for APScheduler + SQLite reminders
├── outputs/                        # Runtime Generated Artifacts (Git-Ignored)
│   ├── events/                     # Generated RFC 5545 .ics calendar files
│   └── [generated_reports.pdf]     # Synthesized academic PDF summaries
├── rag/                            # Core Retrieval-Augmented Generation Pipeline
│   ├── chunking.py                 # Sliding-window token chunker (~500 tokens, 50 overlap)
│   ├── embeddings.py               # Sentence-Transformers all-MiniLM-L6-v2 embedder
│   ├── generator.py                # Grounded answer synthesis & local-to-web fallback
│   ├── ingest.py                   # Multi-format document loader (PDF, DOCX, TXT, MD)
│   ├── retriever.py                # Threshold-gated retrieval engine (tau = 0.30)
│   ├── trust_ranker.py             # Domain authority trust ranker for web sources
│   ├── vectorstore.py              # Persistent ChromaDB wrapper with pysqlite3 patch
│   └── web_search.py               # DuckDuckGo search & page scraping engine
├── tests/                          # Formal Automated Test Suite (124 Passing Tests)
│   ├── test_auth_and_security.py   # 26 tests: bcrypt, lockout, JWT, reset tokens, API gates
│   ├── test_chunking.py            # 5 tests: sliding window token estimation & overlap
│   ├── test_email_regression.py    # 8 tests: Gmail API dispatch, message ID, duplicate guard
│   ├── test_evaluation_runner.py   # 3 tests: evaluation dataset splits & scoring isolation
│   ├── test_gemini_key_rotation.py # 6 tests: key pool rotation, HTTP 429 backoff, masking
│   ├── test_google_calendar_regression.py # 7 tests: Calendar API v3 read-back, timezone, idempotency
│   ├── test_google_services_mcp.py # 4 tests: Google MCP tool registration & diagnostics
│   ├── test_mcp_servers.py         # 8 tests: FastMCP server lifecycles & tool execution
│   ├── test_pdf_download_regression.py # 9 tests: ReportLab PDF synthesis, path traversal sanitization
│   ├── test_planner_executor.py    # 11 tests: Step DAG decomposition, step bounding, safety halting
│   ├── test_rag.py                 # 11 tests: document ingestion, ChromaDB, bracketed citations
│   ├── test_retrieval_threshold.py # 4 tests: cosine distance conversion, refusal gating
│   └── test_web_search_and_trust.py # 22 tests: universal doc-first, trusted web fallback, zero leaks
├── ui/                             # User Interface Layer
│   ├── streamlit_app.py            # Primary interactive Streamlit chat portal & admin gate
│   └── pages/
│       └── 1_Evaluation.py         # Streamlit interactive evaluation & benchmark dashboard
├── .env.example                    # Template environment configuration file
├── pytest.ini                      # Pytest runner configuration
├── README.md                       # Comprehensive project documentation & defense guide
└── requirements.txt                # Pinned Python package dependencies
```

---

## 7. Master File & Component Purpose Table

| File / Directory | Architectural Responsibility | Key Implementation Details | Report Relevance |
|---|---|---|---|
| [`agents/graph.py`](file:///D:/rag-mcp-assistant/agents/graph.py) | Central LangGraph Orchestrator | Compiles `StateGraph(AgentState)` with 8 nodes, conditional routing, and SQLite turn logging | Chapter 5 (System Architecture & State Machine) |
| [`agents/orchestrator.py`](file:///D:/rag-mcp-assistant/agents/orchestrator.py) | Intent Classification | Few-shot LLM routing prompt classifying inputs into `QA`, `ACTION`, `CHAINED`, or `CHAT` | Chapter 4 (Modules) & Chapter 5 (Routing) |
| [`agents/planner.py`](file:///D:/rag-mcp-assistant/agents/planner.py) | Goal Decomposition | Generates structured JSON Step DAGs; enforces 10-step bound and halts on missing data | Chapter 4 (Modules) & Chapter 6 (Implementation) |
| [`agents/rag_agent.py`](file:///D:/rag-mcp-assistant/agents/rag_agent.py) | RAG Execution Node | Queries retriever, evaluates cosine similarity against $\tau=0.30$, routes to generator | Chapter 4 (Modules) & Chapter 5 (RAG Flow) |
| [`agents/action_agent.py`](file:///D:/rag-mcp-assistant/agents/action_agent.py) | Tool Dispatcher | Dispatches to FastMCP client controller, records telemetry, and formats receipts | Chapter 3 (MCP Architecture) |
| [`agents/memory.py`](file:///D:/rag-mcp-assistant/agents/memory.py) | Short-Term Context | Manages `chat_history`, `user_preferences`, and `action_logs` SQLite tables | Chapter 6 (Database & Memory) |
| [`app/auth.py`](file:///D:/rag-mcp-assistant/app/auth.py) | Administrator Security Engine | Salted bcrypt (`rounds=12`), progressive 15-min lockout, JWT revocation, SHA-256 reset tokens | Chapter 6 (Security & Access Control) |
| [`app/auth_email.py`](file:///D:/rag-mcp-assistant/app/auth_email.py) | Restricted Password Reset Emailer | Sends secure password reset links via Google Workspace Gmail API v1 or SMTP fallback | Chapter 6 (Security & Email Subsystem) |
| [`app/config.py`](file:///D:/rag-mcp-assistant/app/config.py) | Unified Settings Manager | Resolves paths, parses comma-separated Gemini keys, falls back from `os.getenv` to `st.secrets` | Chapter 3 (Software Requirements) |
| [`app/routes.py`](file:///D:/rag-mcp-assistant/app/routes.py) | FastAPI Gateway Endpoints | Protected REST endpoints (`/api/chat`, `/api/upload`, etc.) enforcing `get_current_admin` gate | Chapter 5 (API Gateway Layer) |
| [`llm/gemini_client.py`](file:///D:/rag-mcp-assistant/llm/gemini_client.py) | Google Gemini Client | Thread-safe `GeminiKeyManager` pool rotation on HTTP 429, key masking, and backoff | Chapter 6 (LLM & Provider Abstraction) |
| [`mcp_servers/client.py`](file:///D:/rag-mcp-assistant/mcp_servers/client.py) | FastMCP Client Controller | Dynamic discovery of FastMCP servers via `list_tools()`, parameter validation & dispatch | Chapter 4 (MCP Implementation) |
| [`mcp_servers/reminder_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/reminder_server.py) | Local Reminder Microservice | FastMCP server using APScheduler and SQLite for local alerts | Chapter 4 (MCP Server Inventory) |
| [`mcp_servers/calendar_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/calendar_server.py) | Local Calendar Microservice | FastMCP server generating standard RFC 5545 `.ics` files in `outputs/events/` | Chapter 4 (MCP Server Inventory) |
| [`mcp_servers/email_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/email_server.py) | Email Microservice | FastMCP server with mandatory HITL preview and SMTP delivery | Chapter 4 (MCP Server Inventory) |
| [`mcp_servers/pdf_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/pdf_server.py) | PDF Synthesis Microservice | FastMCP server compiling structured ReportLab academic summaries with SHA-256 hashes | Chapter 4 (MCP Server Inventory) |
| [`mcp_servers/google_services_server.py`](file:///D:/rag-mcp-assistant/mcp_servers/google_services_server.py) | Google Workspace Microservice | FastMCP server wrapping Google Calendar v3, Gmail v1, Tasks v1, and Drive v3 REST APIs | Chapter 4 & 6 (External Integrations) |
| [`rag/chunking.py`](file:///D:/rag-mcp-assistant/rag/chunking.py) | Sliding Window Chunker | Splits text into ~500 token windows with 50 token overlap; preserves page metadata | Chapter 4 & 5 (RAG Pipeline) |
| [`rag/embeddings.py`](file:///D:/rag-mcp-assistant/rag/embeddings.py) | Dense Embedder | Local CPU inference using `sentence-transformers/all-MiniLM-L6-v2` (384-d vectors) | Chapter 5 (Embeddings & Vectors) |
| [`rag/vectorstore.py`](file:///D:/rag-mcp-assistant/rag/vectorstore.py) | Vector Database Manager | Wraps ChromaDB persistent client with `pysqlite3` Linux compatibility patch | Chapter 5 & 6 (Vector Database) |
| [`rag/retriever.py`](file:///D:/rag-mcp-assistant/rag/retriever.py) | Threshold-Gated Retriever | Converts Chroma distance to cosine similarity ($\text{sim}=1-d$), enforces $\tau=0.30$ | Chapter 5 & 6 (Anti-Hallucination Gate) |
| [`rag/web_search.py`](file:///D:/rag-mcp-assistant/rag/web_search.py) | DuckDuckGo Web Engine | Scrapes external web content and enforces structured citations | Chapter 5 & 6 (Web Research Fallback) |
| [`rag/trust_ranker.py`](file:///D:/rag-mcp-assistant/rag/trust_ranker.py) | Domain Authority Ranker | Scores web domains into Tier 1 (0.90–1.00), Tier 2 (0.75), Tier 3 (0.50), and Tier 4 (0.20) | Chapter 5 & 6 (Domain Trust Ranking) |
| [`rag/generator.py`](file:///D:/rag-mcp-assistant/rag/generator.py) | Context-Grounded Synthesizer | Formulates grounded prompts, enforces bracketed citations, coordinates hybrid fallback | Chapter 5 & 6 (Response Synthesis) |
| [`ui/streamlit_app.py`](file:///D:/rag-mcp-assistant/ui/streamlit_app.py) | Streamlit User Interface | Primary frontend portal: admin sign-in gate, chat interface, compact settings, telemetry | Chapter 6 (Frontend Implementation) |

---

## 8. Application Entry Points & Execution Sequence

### 8.1 Primary User Interface (Self-Contained Streamlit Portal)
- **File:** [`ui/streamlit_app.py`](file:///D:/rag-mcp-assistant/ui/streamlit_app.py)
- **Command:**
  ```powershell
  python -m streamlit run ui/streamlit_app.py --server.port 8501
  ```
- **Execution Flow:**
  1. Bootstraps environment and initializes directory layout via `Settings.ensure_directories()`.
  2. Applies `pysqlite3` monkey-patch if running under Linux (Streamlit Cloud).
  3. Verifies administrator authentication session; if unauthenticated, renders login portal and calls `st.stop()`.
  4. Once authenticated, loads compact sidebar, document upload widget, and interactive chat interface.
  5. Directly calls `run_assistant(prompt)` in `agents/graph.py` in-process.

### 8.2 Backend REST API Gateway (Alternative Headless Server)
- **File:** [`app/main.py`](file:///D:/rag-mcp-assistant/app/main.py)
- **Command:**
  ```powershell
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
  ```
- **Execution Flow:**
  1. Configures CORS middleware for local frontend communication.
  2. Mounts protected REST routes from [`app/routes.py`](file:///D:/rag-mcp-assistant/app/routes.py).
  3. Exposes interactive Swagger documentation at `http://127.0.0.1:8000/docs`.
  4. Enforces JWT Bearer token authentication via `get_current_admin` dependency on all data and tool endpoints.

---

## 9. Runtime Environment & Dependencies

- **Python Runtime:** Python 3.11.1 (64-bit).
- **Primary Operating System:** Windows 10/11 (PowerShell); deployment compatible with Linux (Debian/Ubuntu) via `pysqlite3-binary`.
- **System Memory:** 8 GB minimum, 16 GB recommended (accommodates local Sentence-Transformers model and ChromaDB index).
- **Disk Space:** 2 GB free disk space for dependencies, PyTorch CPU wheel, ChromaDB collections, and SQLite databases.
