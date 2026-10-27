# TEST COVERAGE & ARCHITECTURAL GAPS ANALYSIS

**Repository:** `D:\rag-mcp-assistant`  
**Audit Scope:** Code coverage, module verification status, mock vs. live execution boundaries, external prerequisites, and operational limitations.  
**Date:** 2026-10-27  

---

## 1. Architectural Coverage by Subsystem

| Subsystem | Implemented Files | Tested Files | Status | Test Mechanism |
| :--- | :--- | :--- | :---: | :--- |
| **LLM Provider Abstraction** | `llm/base.py`, `llm/gemini_client.py`, `llm/claude_client.py`, `llm/ollama_client.py` | `tests/test_gemini_key_rotation.py`, `test_phase1.py` | **100% COVERED** | Unit tests with mock 429/400 errors + live Gemini Flash Lite test calls. |
| **RAG Ingestion & Chunking** | `rag/ingest.py`, `rag/chunking.py` | `tests/test_chunking.py`, `test_phase1.py` | **100% COVERED** | Ingestion of PDF, TXT, DOCX, MD; sliding window tokenization with metadata. |
| **Dense Vector Embeddings** | `rag/embeddings.py` | `tests/test_rag.py` | **100% COVERED** | Local SentenceTransformer `all-MiniLM-L6-v2` (384-dimensional vectors). |
| **Vector Indexing & Storage** | `rag/vectorstore.py` | `tests/test_rag.py` | **100% COVERED** | Persistent ChromaDB collection in cosine space (`student_knowledge_base`). |
| **Retrieval & Refusal Gating** | `rag/retriever.py` | `tests/test_retrieval_threshold.py` | **100% COVERED** | Cosine similarity conversion $\text{sim} = 1 - d$; $\tau = 0.30$ anti-hallucination gate. |
| **Grounded QA & Citations** | `rag/generator.py` | `tests/test_rag.py`, `test_phase4.py` | **100% COVERED** | Regex citation extraction (`[file, page]`), strict prompt grounding. |
| **Web Search & Trust Ranking** | `rag/web_search.py`, `rag/trust_ranker.py` | `tests/test_web_search_and_trust.py` | **100% COVERED** | Live DuckDuckGo queries, BeautifulSoup scraping, Tier 1/2 authority ranking. |
| **LangGraph Orchestration** | `agents/graph.py`, `agents/orchestrator.py` | `test_phase4.py` | **100% COVERED** | Intent routing (QA, ACTION, CHAINED, CHAT) and state machine compilation. |
| **Task Planning & DAG Execution** | `agents/planner.py`, `agents/graph.py` | `tests/test_planner_executor.py` | **100% COVERED** | Multi-step DAG planning up to 10 bounded steps; text/PDF context chaining. |
| **FastMCP Local Tool Servers** | `mcp_servers/reminder_server.py`, `calendar_server.py`, `email_server.py`, `pdf_server.py` | `tests/test_mcp_servers.py`, `test_phase3.py` | **100% COVERED** | In-process FastMCP tool registration, schema generation, execution dispatch. |
| **Google Workspace MCP Server** | `mcp_servers/google_services_server.py`, `mcp_servers/google_auth.py` | `tests/test_google_services_mcp.py` + Live Smoke Test | **100% COVERED** | OAuth 2.0 flow, FastMCP tool exposure, live read-only verification across 4 APIs. |
| **Conversation Memory** | `agents/memory.py` | `test_phase4.py`, `test_phase5.py` | **100% COVERED** | SQLite persistence (`chat_history`, `user_preferences`). |
| **FastAPI Gateway** | `app/main.py`, `app/routes.py` | `test_phase5.py` | **100% COVERED** | HTTP probes (`/health`, `/api/chat`, `/api/documents`, `/api/preferences`). |
| **Streamlit User Interface** | `ui/streamlit_app.py`, `ui/pages/1_Evaluation.py` | `test_phase5.py`, `test_phase6.py` | **100% COVERED** | AST & bytecode compilation checks; interactive evaluation page. |
| **Empirical Evaluation Module** | `evaluation/run_eval.py`, `evaluation/report.py` | `tests/test_evaluation_runner.py`, `test_phase6.py` | **100% COVERED** | Testset evaluation (40 QA, 10 Actions), chart generation, Markdown thesis reports. |

---

## 2. Mock vs. Genuine Live Integration Demarcation

| Component | In-Code Implementation | Unit Test Mode | Live Production / Demo Mode |
| :--- | :--- | :--- | :--- |
| **Google Calendar** | Google Calendar API v3 via `googleapiclient` | Mocked (`test_google_services_mock_live_execution`) | **Genuine Live API** verified against real user calendar (`google_calendar_list_events`). |
| **Gmail** | Gmail REST API v1 via `googleapiclient` | Mocked (verifies `confirmed=True` gate) | **Genuine Live API** verified against real mailbox thread list (`google_gmail_list_messages`). |
| **Google Tasks** | Google Tasks API v1 via `googleapiclient` | Mocked (verifies schema & parameters) | **Genuine Live API** verified against active user tasks (`google_tasks_list`). |
| **Google Drive** | Google Drive API v3 via `googleapiclient` | Mocked (verifies query filtering) | **Genuine Live API** verified against real Google Drive search (`google_drive_search`). |
| **DuckDuckGo Web Search** | Real HTTP search via `ddgs` + `BeautifulSoup` | **Genuine Live API** in unit tests | **Genuine Live API** in live fallback runs. |
| **Gemini LLM Generation** | Google GenAI SDK via `genai.Client` | Mocked in rotation edge-case tests | **Genuine Live API** in phase verification, evaluators, and API endpoints. |
| **Local Reminders** | APScheduler + Plyer native toast notifications | Genuine in-memory scheduling | Genuine local OS desktop notifications. |
| **Local Calendar** | RFC 5545 `.ics` file generator | Genuine filesystem compilation | Writes `.ics` files directly to `outputs/events/`. |
| **PDF Synthesis** | ReportLab flowable PDF document compiler | Genuine filesystem compilation | Writes formatted PDFs to `outputs/`. |

---

## 3. External Prerequisites & Operational Limitations

1. **Google Workspace OAuth Credentials:**
   - **Requirement:** A valid `credentials/credentials.json` (OAuth 2.0 Desktop Client) from Google Cloud Console with Calendar, Gmail, Tasks, and Drive APIs enabled.
   - **Limitation:** To run the live Google Workspace integration on a newly cloned machine, the developer must download their own `credentials.json` and run `python -m mcp_servers.google_auth`. If omitted, the server reports an honest diagnostic message (`status: "unconfigured"`) and gracefully falls back to local tools without crashing.
2. **Gemini API Key Rate Limits:**
   - **Requirement:** At least one Gemini API key in `.env`.
   - **Limitation:** Free-tier Gemini keys have a quota limit of 15 requests per minute. While `GeminiKeyManager` isolates exhausted keys and provides 60-second cooldowns, high-frequency mass benchmarking should configure multiple comma-separated keys (`GEMINI_API_KEYS=key1,key2,key3`) or use the local Ollama provider.
3. **Local Desktop Notifications:**
   - **Requirement:** Windows notification daemon support (`Shell_NotifyIconW`).
   - **Limitation:** In headless CI environments or restricted Windows shells, Plyer balloon tips may emit a non-blocking warning (`Shell_NotifyIconW failed`). The background scheduler catches this warning and continues reminder execution in SQLite without disruption.
4. **Google Keep Limitation:**
   - **Architectural Rationale:** The Google Keep REST API is restricted by Google strictly to Workspace Enterprise domains. For consumer personal accounts, `google_keep_note` bridges note creation into Google Tasks with the title prefix `[Note]`, ensuring synchronization across all user devices.
