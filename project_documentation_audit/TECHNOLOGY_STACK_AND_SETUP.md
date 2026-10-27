# Technology Stack and Developer Setup Guide

**Audit Standard:** Strict Verification of `D:\rag-mcp-assistant\requirements.txt` & Code Imports  
**Target Runtime:** Python 3.11.1 on Windows 10/11 or Linux (Ubuntu 22.04+)

---

## 1. Verified Technology & Dependency Inventory

| Technology / Library | Pinned Version | Layer / Role | Where Used | Architectural Justification | Required at Runtime? |
|---|---|---|---|---|:---:|
| **Python** | 3.11.1 (64-bit) | Runtime Environment | Entire Project | Fast runtime, modern type annotations (`TypedDict`, `from __future__ import annotations`) | **Yes** |
| **Streamlit** | `>=1.38.0` | User Interface | `ui/streamlit_app.py`, `ui/pages/` | Reactive web UI, custom CSS theming, session management, in-chat PDF downloads | **Yes** |
| **FastAPI** | `>=0.115.0` | API Gateway Layer | `app/main.py`, `app/routes.py` | Asynchronous REST endpoints, Swagger docs, dependency injection (`Depends`) | Optional (if running UI only) |
| **Uvicorn** | `>=0.30.0` | ASGI Web Server | `app/main.py` | Lightning-fast ASGI production server for FastAPI gateway | Optional |
| **LangGraph** | `>=0.2.20` | Multi-Agent Orchestrator | `agents/graph.py` | Stateful graph orchestration, cyclic execution, dynamic DAG state transitions | **Yes** |
| **LangChain-Core** | `>=0.3.0` | Agent Base Primitives | `agents/` | Base prompt message containers and state abstractions | **Yes** |
| **FastMCP** | `mcp>=1.0.0,<2.0.0` | Model Context Protocol | `mcp_servers/` | Official Anthropic FastMCP Python SDK for dynamic client-server tool discovery | **Yes** |
| **ChromaDB** | `>=0.5.5` | Persistent Vector Store | `rag/vectorstore.py` | Local disk-backed vector database with SQLite metadata storage | **Yes** |
| **pysqlite3-binary** | Latest | Linux SQLite Shim | `rag/vectorstore.py`, `ui/streamlit_app.py` | Overcomes older SQLite versions in Linux cloud containers (Streamlit Cloud) | Linux only |
| **Sentence-Transformers** | `>=3.0.1` | Local Dense Embeddings | `rag/embeddings.py` | `all-MiniLM-L6-v2` dense 384-d semantic embeddings running on local CPU | **Yes** |
| **PyTorch (`torch`)** | `>=2.2.0` | Neural Inference Engine | Transitive dependency of `sentence-transformers` | Executes transformer tensor operations locally on CPU | **Yes** |
| **Google GenAI** | `>=0.8.0` | Primary LLM Provider | `llm/gemini_client.py` | Google Gemini 1.5 Flash Lite API client with thread-safe key pool rotation | **Yes** |
| **Anthropic SDK** | `>=0.34.0` | Alternative LLM Provider | `llm/claude_client.py` | Claude 3.5 Sonnet client for multi-provider benchmarking | Optional |
| **DuckDuckGo Search (`ddgs`)**| `>=9.0.0` | Web Research Engine | `rag/web_search.py` | Anonymous, rate-limit tolerant external web research and snippet extraction | **Yes** |
| **BeautifulSoup4** | `>=4.12.0` | HTML Web Parser | `rag/web_search.py` | Extracts clean body text from external web pages during research fallback | **Yes** |
| **ReportLab** | `>=4.2.2` | PDF Compilation Engine | `mcp_servers/pdf_server.py` | Generates publication-quality formatted PDF notes, summaries, and exam schedules | **Yes** |
| **PyPDF** | `>=4.3.1` | Document Ingestion | `rag/ingest.py` | Parses uploaded `.pdf` documents with 1-indexed page extraction | **Yes** |
| **python-docx** | `>=1.1.2` | Document Ingestion | `rag/ingest.py` | Parses uploaded Microsoft Word `.docx` syllabi and notes | **Yes** |
| **ICS** | `>=0.7.2` | Calendar Generator | `mcp_servers/calendar_server.py` | Compiles standard RFC 5545 `.ics` calendar files for desktop/mobile imports | **Yes** |
| **APScheduler** | `>=3.10.4` | Background Scheduler | `mcp_servers/reminder_server.py` | In-memory background thread scheduling for local reminder firing | **Yes** |
| **Plyer** | `>=2.1.0` | Native OS Notifications | `mcp_servers/reminder_server.py` | Triggers native Windows/macOS/Linux desktop notification toasts | **Yes** |
| **Google Auth & OAuthlib** | `>=1.2.0` | OAuth 2.0 Client | `mcp_servers/google_auth.py` | Google OAuth desktop client flow, token refresh, and credential persistence | Optional |
| **Google API Client** | `>=2.140.0` | Google Services SDK | `mcp_servers/google_services_server.py` | Official client library for Google Calendar v3, Gmail v1, Tasks, and Drive | Optional |
| **Bcrypt** | `>=4.0.0` | Password Hashing | `app/auth.py` | Cryptographically secure salted password hashing (`rounds=12`) | **Yes** |
| **PyJWT** | `>=2.8.0` | Session Token Security | `app/auth.py` | Signs and verifies HMAC-SHA256 JWT tokens for administrator sessions | **Yes** |
| **Cryptography** | `>=42.0.0` | Cryptographic Primitives | Transitive / `app/auth.py` | Underlying cryptographic primitives for SSL, token signing, and hashing | **Yes** |
| **Pydantic** | `>=2.8.0` | Data Validation | `app/config.py`, `app/routes.py` | Runtime type validation, schema serialization, and settings parsing | **Yes** |
| **Python-Dotenv** | `>=1.0.1` | Environment Loader | `app/config.py` | Loads secrets and hyperparameters from project root `.env` | **Yes** |
| **Pytest** | `>=8.0.0` | Testing Framework | `tests/` | Test runner and assertion library for 124 formal automated tests | Dev / Test |
| **Playwright** | `>=1.45.0` | Headless Browser Testing | `audit/` | Automates end-to-end browser audits, captures verification screenshots | Dev / Test |

---

## 2. Fresh Developer Machine Setup Guide

Follow this sequence to set up the project on a clean developer workstation:

### Step 1: Clone Repository
```powershell
Set-Location "D:\"
git clone https://github.com/anandshankar-creator/rag-mcp-assistant.git
Set-Location "D:\rag-mcp-assistant"
```

### Step 2: Create and Activate Virtual Environment
```powershell
# Create virtual environment using Python 3.11
python -m venv venv

# Activate on Windows PowerShell:
.\venv\Scripts\Activate.ps1

# (Or on Linux / macOS Bash:)
# source venv/bin/activate
```

### Step 3: Install Package Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Local Environment Variables
Copy the template configuration file to `.env`:
```powershell
Copy-Item .env.example .env
```
Open `.env` in an editor and supply your credentials:
```ini
# Primary LLM Provider
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...your_gemini_api_key_here
# Optional multiple keys for quota rotation:
# GEMINI_API_KEYS=key1,key2,key3
GEMINI_MODEL=gemini-flash-lite-latest

# Administrator Authentication Credentials
ADMIN_EMAIL=admin@assistant.local
ADMIN_INITIAL_PASSWORD=AdminSecurePass2026!
JWT_SECRET_KEY=change-to-a-cryptographically-secure-random-32-char-string
SESSION_EXPIRE_MINUTES=120
RESET_TOKEN_EXPIRE_MINUTES=15
APP_BASE_URL=http://localhost:8501

# RAG & Trust Search Hyperparameters
RAG_SIMILARITY_THRESHOLD=0.30
RAG_TOP_K=4
ENABLE_WEB_FALLBACK=true
WEB_SEARCH_MIN_TRUST=0.45
TIMEZONE=Asia/Kolkata
USER_NAME=Student
```

### Step 5: (Optional) Google Workspace Desktop OAuth Setup
If enabling real Google Calendar or Gmail API integrations:
1. Place your Google Cloud desktop credentials file at `credentials/credentials.json`.
2. Run the interactive one-time authorization:
   ```powershell
   python -m mcp_servers.google_auth
   ```
   This opens your browser for Google account consent and generates `credentials/google_token.json`.

---

## 3. Launching the Application

### Option A: Launch Interactive Streamlit Assistant (Primary Portal)
```powershell
Set-Location "D:\rag-mcp-assistant"
streamlit run ui/streamlit_app.py --server.port 8501
```
Open your browser at `http://localhost:8501`. Log in with your configured `ADMIN_EMAIL` and `ADMIN_INITIAL_PASSWORD`.

### Option B: Launch Headless FastAPI Gateway (REST Server)
```powershell
Set-Location "D:\rag-mcp-assistant"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Interactive OpenAPI documentation will be accessible at `http://127.0.0.1:8000/docs`.

---

## 4. Running the Complete Verification Test Suite

```powershell
# Run all 124 formal unit, integration, and security tests:
pytest

# Run all 149 tests (including legacy phase harness tests):
pytest -o testpaths="tests ."
```
Expected output: **124 passed in ~8.0s (100% pass rate)**.
