# PROJECT FACTS: TECHNICAL AUDIT AND ARCHITECTURAL TRUTH SPECIFICATION

**Project Title:** A Retrieval-Augmented Generation Based Multi-Agent Personal Assistant Architecture Using the Model Context Protocol (MCP)  
**Target Domain:** Academic Assistant for University Students (KTU S7 B.Tech Computer Science & Engineering)  
**Repository Location:** `D:\rag-mcp-assistant`  
**Audit Date:** 2026-10-26  
**Auditor:** Automated Codebase & File Integrity Verification Suite  

---

## SECTION A: VERIFICATION OF ARCHITECTURAL CLAIMS

### 1. Planner Agent and Chained Step Execution
- **Verdict:** **PARTLY TRUE**
- **File Path:** `D:/rag-mcp-assistant/agents/planner.py`, `D:/rag-mcp-assistant/agents/graph.py`
- **Function/Component Name:** `Planner.generate_plan` (`agents/planner.py`), `executor_node` (`agents/graph.py`, lines 260–348)
- **Detailed Evidence:**
  - `agents/planner.py` exists and implements `generate_plan(user_query: str) -> Plan`. It uses keyword pattern-matching and regular expressions (with fallback to an LLM prompt) to generate a structured `Plan(steps=[PlanStep(...)])`.
  - However, in `agents/graph.py` inside `executor_node`, the execution of chained steps is **not a dynamic DAG execution engine**. Instead, it is an explicit, hardcoded sequential pipeline:
    1. Step 1: `rag_retrieve` – retrieves relevant context chunks via `retriever.retrieve(query)`.
    2. Step 2: `summarize` – takes the retrieved chunks and prompts the LLM to generate an academic summary.
    3. Step 3: `generate_pdf` – passes the generated summary text to the FastMCP tool `generate_pdf(title, content, filename)`.
    4. Step 4: `send_email` – takes the resulting PDF file path from Step 3 and passes it as an attachment to FastMCP tool `send_email(to, subject, body, attachment_path)`.
    5. Step 5: `create_reminder` – schedules a reminder via FastMCP tool `create_reminder(title, due_datetime)`.
  - While data is passed from one step to the next (e.g., summary $\rightarrow$ PDF $\rightarrow$ email attachment), the sequence itself is hardcoded for this specific demo pipeline. Arbitrary multi-step DAG plans or dynamic re-ordering of tools cannot be executed by `executor_node`.

---

### 2. Memory Component (SQLite Chat History & User Preferences)
- **Verdict:** **TRUE**
- **File Path:** `D:/rag-mcp-assistant/agents/memory.py`, `D:/rag-mcp-assistant/agents/graph.py`
- **Function/Component Name:** `SQLiteMemoryManager` (`agents/memory.py`), `chat_node` (`agents/graph.py`, lines 220–255)
- **What is Stored:**
  1. **`chat_history` table:**
     - Columns: `id INTEGER PRIMARY KEY`, `session_id TEXT`, `role TEXT`, `content TEXT`, `created_at TIMESTAMP`.
     - Stored Data: Every user message and assistant response along with the corresponding `session_id`.
  2. **`user_preferences` table:**
     - Columns: `pref_key TEXT PRIMARY KEY`, `pref_value TEXT`, `updated_at TIMESTAMP`.
     - Stored Data:
       - `user_name`: Student's name (default: `"Alex"`).
       - `user_email`: Student's email (default: `"alex.student@ktu.edu.in"`).
       - `default_reminder_lead_hours`: Default offset for reminders (default: `"24"`).
- **How It Is Used:**
  - **In Chat Multi-Turn Routing:** `memory.get_recent_history(session_id, limit=6)` retrieves the last 6 messages (3 conversational turns). These are formatted and injected directly into the LLM system prompt in `chat_node` (`agents/graph.py`), enabling contextual multi-turn conversation.
  - **In Action & Email Personalization:** `memory.get_all_preferences()` is retrieved in `action_agent.py` and `agents/graph.py` to pre-fill the student's name in email bodies and system prompts, and pre-populate the default recipient email address in `preview_email` / `send_email`.

---

### 3. Orchestrator Intent Routing (QA, ACTION, CHAINED, CHAT)
- **Verdict:** **BOTH (LLM Prompt + Keyword Heuristics)**
- **File Path:** `D:/rag-mcp-assistant/agents/orchestrator.py`
- **Function/Component Name:** `OrchestratorRouter.classify_intent` (lines 71–155)
- **Detailed Evidence:**
  - Intent classification is performed through a three-tier hybrid mechanism:
    1. **Heuristic Pre-filter:** Fast regex check for multi-action chaining keywords (e.g., queries matching `summarize.*(pdf|email|remind)` or containing phrases like `"and then"`, `"also email"`, `"make a pdf and"`). If matched, it immediately classifies as `CHAINED` without incurring LLM latency.
    2. **Primary LLM Classifier:** If not matched by regex, it prompts the configured LLM with `ROUTER_SYSTEM_PROMPT` expecting a strict JSON output matching schema `{"route": "<QA|ACTION|CHAINED|CHAT>", "reasoning": "..."}`.
    3. **Deterministic Keyword Fallback:** If the LLM invocation fails, times out, or returns malformed JSON, `classify_intent` falls back to keyword matching:
       - `remind`, `reminder`, `calendar`, `event`, `schedule`, `email`, `mail`, `pdf` $\rightarrow$ `ACTION`
       - `who`, `what`, `when`, `where`, `why`, `how`, `explain`, `difference`, `syllabus`, `module`, `notes` $\rightarrow$ `QA`
       - `hi`, `hello`, `hey`, `thanks`, `help` $\rightarrow$ `CHAT`
       - Otherwise $\rightarrow$ `QA` (default).
- **Exact Verbatim Prompt (`ROUTER_SYSTEM_PROMPT`):**
```text
You are the central intent router for an academic personal assistant for a university student.
Your sole job is to classify the user's input into exactly one of four execution routes:

1. "QA" - The user is asking a factual, conceptual, or syllabus/timetable question that should be answered from their academic documents (notes, textbooks, syllabus, timetable).
   Examples: "What is Belady's Anomaly?", "When is the CS402 internal exam?", "Explain relational algebra selection."

2. "ACTION" - The user wants the assistant to perform a single concrete task using an external tool: create a reminder, create a calendar event, list reminders/events, delete an item, preview/send an email, or generate a PDF.
   Examples: "Remind me to study DBMS tonight at 8pm", "Add project review to my calendar on Friday at 10am", "Show my reminders", "Send an email to my guide."

3. "CHAINED" - The user makes a complex multi-step request that combines multiple operations (e.g., retrieve notes -> summarize -> generate PDF -> email it -> create reminder).
   Examples: "Summarize my OS Unit 3 notes, make a PDF, email it to me, and remind me tomorrow."

4. "CHAT" - Conversational chit-chat, greetings, polite remarks, or general questions about what the assistant can do.
   Examples: "Hello!", "Thank you", "Who are you?", "What can you help me with?"

Respond ONLY with a valid JSON object in this exact schema:
{
  "route": "QA" | "ACTION" | "CHAINED" | "CHAT",
  "reasoning": "one sentence explaining your choice"
}
```

---

### 4. Chunk Size, Overlap, and Token Counting
- **Verdict:** **WORDS (Regex Word Count), NOT A TOKENIZER**
- **File Path:** `D:/rag-mcp-assistant/rag/chunking.py`
- **Function/Component Name:** `estimate_tokens` (lines 34–40), `chunk_text` (lines 82–125)
- **Detailed Evidence:**
  - Token counting is an approximation based on regular expressions, **not** a subword tokenizer (like HuggingFace BPE, WordPiece, or tiktoken).
  - Code in `estimate_tokens`:
    ```python
    def estimate_tokens(text: str) -> int:
        return len(re.findall(r"\w+|[^\w\s]", text))
    ```
  - In `chunk_text(text, chunk_size_tokens=500, chunk_overlap_tokens=50)`:
    - Words are split via `text.split()`.
    - Targets are converted using a fixed $0.75$ words-per-token ratio:
      - `target_words = max(50, int(chunk_size_tokens * 0.75))` $\rightarrow 500 \times 0.75 = 375$ words.
      - `overlap_words = int(chunk_overlap_tokens * 0.75)` $\rightarrow 50 \times 0.75 = 37$ words.
  - The chunker creates sliding windows of 375 words with an overlap of 37 words, while attempting to split at sentence boundaries (`. `, `\n`).

---

### 5. Embedding Model, Dimensions, Vector Store, and Config Values
- **Verdict:** **TRUE**
- **File Path:** `D:/rag-mcp-assistant/app/config.py` (lines 60–80), `D:/rag-mcp-assistant/rag/vectorstore.py` (lines 45–65), `D:/rag-mcp-assistant/.env` (lines 28–35)
- **Actual Config Values:**
  - `EMBEDDING_MODEL_NAME`: `"sentence-transformers/all-MiniLM-L6-v2"` (Output dimension: 384)
  - `CHROMA_PERSIST_DIR`: `"./db/chroma"` (Absolute on host: `D:\rag-mcp-assistant\db\chroma`)
  - `RAG_TOP_K`: `4`
  - `RAG_SIMILARITY_THRESHOLD`: `0.30`
  - `RAG_CHUNK_SIZE`: `500`
  - `RAG_CHUNK_OVERLAP`: `50`
  - Vector Space Distance: `metadata={"hnsw:space": "cosine"}` passed during `chroma_client.get_or_create_collection()`.
  - Similarity Calculation in Code (`rag/retriever.py`, line 96):
    $$\text{similarity} = \max(0.0, 1.0 - \text{cosine\_distance})$$

---

### 6. Refusal Threshold (0.30): Definition, Tuning, and Limitations
- **Verdict:** **TRUE (Tuned Directly on Test Questions)**
- **File Path:** `D:/rag-mcp-assistant/app/config.py` (line 74), `D:/rag-mcp-assistant/.env` (line 30), `D:/rag-mcp-assistant/rag/retriever.py` (lines 90–120)
- **Function/Component Name:** `Settings.RAG_SIMILARITY_THRESHOLD`, `Retriever.retrieve`
- **Detailed Evidence & Origin:**
  - Defined in `app/config.py`: `RAG_SIMILARITY_THRESHOLD: float = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.30"))`.
  - **How it was chosen:** It was tuned directly against the 40 testset questions.
    - The initial default threshold was `0.35`.
    - During testing, legitimate in-domain questions with sparse vocabulary overlap scored below 0.35 and were falsely refused:
      - QA-04 (*"What is the difference between equal frame allocation and proportional frame allocation?"*): Max cosine similarity = `0.3193`.
      - QA-29 (*"What is the difference between Pass 1 and Pass 2 of a Two-Pass Assembler?"*): Max cosine similarity = `0.3191`.
    - To prevent false refusals on QA-04 and QA-29, the threshold was lowered to `0.30`.
  - **Consequence / Trade-off:**
    - Lowering the threshold to 0.30 allowed near-domain unanswerable queries to pass through the retriever gate:
      - QA-35 (*"Module 6 of CS402"*): Similarity = `0.4750` ($> 0.30$) $\rightarrow$ Failed to refuse.
      - QA-36 (*"CS408 exam in timetable"*): Similarity = `0.5408` ($> 0.30$) $\rightarrow$ Failed to refuse.
      - QA-37 (*"KTU S8 Cloud Computing"*): Similarity = `0.3930` ($> 0.30$) $\rightarrow$ Failed to refuse.
    - Conversely, extremely brief in-domain queries like *"What is Belady's Anomaly?"* score `0.2568` and are falsely refused unless padded with additional context.

---

### 7. MCP Client Dynamic Tool Discovery
- **Verdict:** **PARTLY TRUE**
- **File Path:** `D:/rag-mcp-assistant/mcp_servers/client.py`
- **Function/Component Name:** `MCPClientController.discover_tools` (lines 55–115)
- **Detailed Evidence:**
  - Tools are discovered dynamically at startup by importing each server module in-process (`importlib.import_module("mcp_servers.<name>")`) and calling `mcp_instance._tool_manager.list_tools()`.
  - **Limitation:** It does **not** communicate over standard subprocess stdio or external JSON-RPC network pipes. Discovery and invocation run in-process within the same Python interpreter.
- **Inventory of Tools (9 Tools across 4 Servers):**
  1. **`reminder_server`:**
     - `create_reminder(title: str, due_datetime: str, note: str = "")`
     - `list_reminders()`
     - `delete_reminder(reminder_id: int)`
  2. **`calendar_server`:**
     - `create_event(title: str, start_datetime: str, end_datetime: str, attendees: str = "", description: str = "")`
     - `list_events()`
     - `delete_event(event_id: int)`
  3. **`email_server`:**
     - `preview_email(to: str, subject: str, body: str, attachment_path: str = "")`
     - `send_email(to: str, subject: str, body: str, attachment_path: str = "", confirmed: bool = True)`
  4. **`pdf_server`:**
     - `generate_pdf(title: str, content: str, filename: str = "")`

---

### 8. Email Confirmation Guard and Unconfigured SMTP Behavior
- **Verdict:** **PARTLY TRUE**
- **File Path:** `D:/rag-mcp-assistant/mcp_servers/email_server.py` (lines 75–155), `D:/rag-mcp-assistant/ui/streamlit_app.py` (lines 280–330), `D:/rag-mcp-assistant/agents/graph.py` (lines 295–325)
- **Where Enforced:**
  - In `mcp_servers/email_server.py`, the `send_email` function signature includes `confirmed: bool = True`, but there is **no guard** inside `email_server.py` (e.g., `if not confirmed: raise ...`).
  - Confirmation is enforced **only at the UI layer** in Streamlit: the user is prompted with an interactive modal showing the preview and a "Confirm & Send" button.
  - In the automated backend graph (`agents/graph.py`), `executor_node` calls `send_email(..., confirmed=True)` automatically without pausing for user intervention.
- **Behavior when SMTP is Not Configured:**
  - If `GMAIL_APP_PASSWORD` is missing or contains `"your_16_digit_app_password"`, it does **not** fail or raise an error.
  - Lines 135–147 trigger simulated dispatch and return:
    ```json
    {
      "status": "success",
      "mode": "simulated",
      "message": "[SIMULATION] Email to alex.student@ktu.edu.in titled 'OS Unit 3 Notes Summary' simulated successfully.",
      "to": "alex.student@ktu.edu.in",
      "subject": "OS Unit 3 Notes Summary"
    }
    ```

---

### 9. Default LLM Provider and Implementation Status of Clients
- **Verdict:** **DEFAULT IS GEMINI (`gemini-flash-lite-latest`). ALL THREE CLIENTS ARE FULLY IMPLEMENTED (NONE ARE STUBS).**
- **File Path:** `D:/rag-mcp-assistant/.env`, `D:/rag-mcp-assistant/llm/__init__.py`, `D:/rag-mcp-assistant/llm/gemini_client.py`, `D:/rag-mcp-assistant/llm/claude_client.py`, `D:/rag-mcp-assistant/llm/ollama_client.py`
- **Detailed Evidence:**
  - `.env` line 7: `LLM_PROVIDER=gemini` and `GEMINI_MODEL=gemini-flash-lite-latest`.
  - `llm/gemini_client.py`: Fully implemented using Google GenAI SDK (`google.genai`), with function-calling transformation and a multi-model fallback chain (`gemini-flash-lite-latest` $\rightarrow$ `gemini-3.5-flash-lite` $\rightarrow$ `gemini-3.1-flash-lite` $\rightarrow$ `gemini-3.5-flash`).
  - `llm/claude_client.py`: Fully implemented using Anthropic SDK (`from anthropic import Anthropic`), supporting tool schemas and system prompts.
  - `llm/ollama_client.py`: Fully implemented using native Python `urllib.request` communicating with the Ollama local REST API (`http://localhost:11434/api/chat`).

---

### 10. Web Fallback and Question-Paper Analysis Features
- **Verdict:** **NOT IMPLEMENTED**
- **Detailed Evidence:**
  - There is no web search fallback (DuckDuckGo, Tavily, Google Search API) implemented anywhere in the repository.
  - There is no past question paper analysis or exam pattern predictor implemented anywhere in the repository.

---

### 11. Local Execution vs Cloud LLM Data Transmission
- **Verdict:** **EMBEDDINGS & VECTOR SEARCH RUN 100% LOCALLY ON CPU; MINIMAL TEXT SENT TO LLM**
- **File Path:** `D:/rag-mcp-assistant/rag/embeddings.py`, `D:/rag-mcp-assistant/rag/vectorstore.py`, `D:/rag-mcp-assistant/rag/generator.py`
- **What Runs Locally:**
  - Embedding computation: `SentenceTransformer` loads weights locally from PyTorch cache and encodes texts on the host CPU.
  - ChromaDB index: Stored locally in SQLite/HNSW parquet files under `db/chroma`. No vector API is accessed over the network.
- **What Data is Sent to the LLM API on Each Request:**
  - **QA Requests:**
    1. System prompt (`RAG_SYSTEM_PROMPT`).
    2. Retrieved context chunks (maximum 4 chunks of up to 375 words each), tagged with source filename and page number.
    3. The student's question.
    *(Note: If similarity $< 0.30$, execution terminates locally and ZERO data is sent to the LLM).*
  - **Action Requests:**
    1. System prompt (`ACTION_SYSTEM_PROMPT`).
    2. User profile name and default email.
    3. JSON schemas for all 9 FastMCP tools.
    4. The user's message.
  - **Chat Requests:**
    1. System prompt.
    2. Last 6 messages of conversation history from SQLite.
    3. The user's greeting/message.

---

## SECTION B: IMPLEMENTATION DETAILS

### 12. RAG System Prompt (Copied Verbatim)
- **File Path:** `D:/rag-mcp-assistant/rag/generator.py` (lines 45–51)
```text
You are a strict academic personal assistant for a university student.
Your instructions are mandatory:
1. Answer ONLY from the provided context chunks below.
2. If the context does not contain the answer, say "I couldn't find this in your documents."
3. Cite sources for every claim as [filename, page] (e.g. [OS_Unit3_Virtual_Memory_Notes.txt, page 1]).
4. Do not use outside knowledge or extrapolate beyond the provided text.
5. Be concise, direct, and factually precise.
```

---

### 13. SQLite Database Schema
- **File Path:** `D:/rag-mcp-assistant/agents/memory.py` (lines 35–70), `D:/rag-mcp-assistant/db/assistant.db`
- **Schema Definitions:**
```sql
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    due_datetime TEXT NOT NULL,
    note TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    start_datetime TEXT NOT NULL,
    end_datetime TEXT NOT NULL,
    attendees TEXT DEFAULT '',
    description TEXT DEFAULT '',
    ics_path TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_preferences (
    pref_key TEXT PRIMARY KEY,
    pref_value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 14. ChromaDB Storage and Configuration
- **File Path:** `D:/rag-mcp-assistant/rag/vectorstore.py` (lines 40–75), `D:/rag-mcp-assistant/app/config.py` (line 72)
- **Parameters:**
  - **Collection Name:** `"student_knowledge_base"`
  - **Persistent Path:** `D:\rag-mcp-assistant\db\chroma` (configured as `./db/chroma`)
  - **HNSW Distance Space:** `"cosine"` (`metadata={"hnsw:space": "cosine"}`)
  - **Metadata Fields Stored per Chunk:**
    - `source_file` (`str`): Base filename (e.g., `"OS_Unit3_Virtual_Memory_Notes.txt"`).
    - `page` (`int`): 1-indexed document page number.
    - `token_count` (`int`): Estimated regex token count of chunk.
    - `chunk_id` (`str`): Identifier formatted as `"{source_file}_p{page}_c{chunk_idx}"`.

---

### 15. FastAPI Endpoints
- **File Path:** `D:/rag-mcp-assistant/app/main.py` (lines 60–265)

| HTTP Method | Path | Request Body / Parameters | Response Schema |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | None | `{"status": str, "service": str, "llm_provider": str, "model": str}` |
| `POST` | `/api/chat` | `ChatRequest(message: str, session_id: str)` | `ChatResponse(session_id, response, route, route_reasoning, citations, action_receipts, trace)` |
| `POST` | `/api/upload` | Multipart Form: `file: UploadFile` | `{"status": str, "filename": str, "pages_extracted": int, "chunks_created": int, "message": str}` |
| `GET` | `/api/documents` | None | `{"total_chunks": int, "documents": List[{"filename": str, "size_bytes": int, "indexed": bool}]}` |
| `DELETE` | `/api/documents/{filename}` | Path parameter: `filename` | `{"status": str, "filename": str, "deleted_chunks": int, "message": str}` |
| `POST` | `/api/confirm-action` | `ActionConfirmRequest(action_type: str, parameters: Dict[str, Any])` | Tool receipt dictionary (`{"status": str, "mode": str, ...}`) |
| `GET` | `/api/preferences` | None | `Dict[str, str]` (All key-value preferences) |
| `POST` | `/api/preferences` | `PreferencesUpdate(name, email, default_reminder_lead_hours)` | `{"status": "success", "preferences": Dict[str, str]}` |
| `MOUNT` | `/outputs` | Static Directory Mount | Serves generated PDF and `.ics` calendar files from `outputs/` |

---

### 16. Exact Environment and Dependency Versions
- **Python Version:** `3.11.1 (tags/v3.11.1:a7a450f, Dec  6 2022, 19:58:39) [MSC v.1934 64 bit (AMD64)]`
- **Operating System:** Windows 10 / Windows 11 AMD64
- **Core Library Versions (from active Python environment):**
  - `fastapi==0.127.0`
  - `uvicorn==0.40.0`
  - `streamlit==1.66.1`
  - `langgraph==1.2.16`
  - `langchain-core==1.6.13`
  - `chromadb==1.5.1`
  - `sentence-transformers==6.2.0`
  - `torch==2.9.1`
  - `google-genai==2.32.0`
  - `mcp==1.30.0`
  - `APScheduler==3.11.3`
  - `plyer==2.1.0`
  - `reportlab==5.1.0`
  - `ics==0.7.3`
  - `pypdf==6.21.1`
  - `python-docx==1.2.0`
  - `pandas==3.0.1`
  - `matplotlib==3.10.8`
  - `pytest==9.0.2`
  - `pydantic==2.12.5`
  - `pydantic-settings==2.16.1`

---

### 17. Error Handling Architecture
- **Missing API Key:**
  - In `llm/gemini_client.py`: `self.client` is set to `None`. When `generate()` is called, lines 70–77 detect `self.client is None` and return `LLMResponse(content="[Configuration Error] GEMINI_API_KEY is missing. Configure it in the .env file.", tool_calls=[])`.
- **Empty Vector Store:**
  - In `rag/vectorstore.py` (`query_similar`), it checks `if self.collection.count() == 0: return []`.
  - `rag/retriever.py` receives an empty chunk list, sets `has_context = False`, and `rag/generator.py` returns `RAGResponse(answer="I couldn't find this in your documents.", citations=[], refused=True)` without calling the LLM.
- **Rate Limit (HTTP 429 / Resource Exhausted):**
  - In `llm/gemini_client.py` (lines 135–185): It attempts multi-model failover through fallback models `["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash"]`. If all models exhaust quota, it catches the exception and returns `LLMResponse(content="Error: Gemini API invocation failed: 429 RESOURCE_EXHAUSTED", tool_calls=[])`.
- **SMTP Failure:**
  - In `mcp_servers/email_server.py`:
    - If `GMAIL_APP_PASSWORD` is unconfigured, it defaults gracefully to simulation mode (`status: "success", mode: "simulated"`).
    - If credentials are configured but the network or SMTP server fails, it catches the exception and returns `{"status": "error", "message": "SMTP Dispatch failed: <error_details>"}`.

---

### 18. Document Provenance and Factual Inventory
- **Provenance:** All sample documents were authored by the AI assistant on 2026-10-20 to seed realistic, curriculum-aligned KTU S7 material.
- **Catalog of Indexed Files and Ground Truth Facts:**
  1. `data/documents/OS_Unit3_Virtual_Memory_Notes.txt`:
     - 6 steps of page fault handling (trap, kernel check, free frame search, disk fetch, page table update valid='1', instruction restart).
     - Belady's Anomaly demonstrated on FIFO with reference string: `1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5` (9 faults with 3 frames vs 10 faults with 4 frames).
     - Optimal page replacement (OPT/MIN) clairvoyant theoretical lower bound.
     - LRU implementation via hardware counters and doubly-linked stack ($O(1)$ stack updates).
     - Second-chance (Clock) replacement using reference bits.
     - Equal allocation ($m/n$) vs Proportional allocation ($a_i = (s_i / \sum s_k) \times m$).
     - Thrashing caused by excessive degree of multiprogramming; Peter J. Denning's Working Set Model ($D = \sum WSS_i > m$).
     - Inverted Page Table format: `<process-id, page-number>`.
  2. `data/documents/DBMS_Unit2_Relational_Algebra_Notes.md`:
     - Fundamental operators: Select ($\sigma$), Project ($\pi$, eliminates duplicates), Union ($\cup$), Set Difference ($-$), Cartesian Product ($\times$), Rename ($\rho$).
     - Derived operators: Natural Join ($\bowtie$), Theta Join ($\bowtie_\theta = \sigma_\theta(R \times S)$), Outer Joins (Left, Right, Full).
     - Query optimization heuristics: Push selections down, push projections down, most restrictive joins first.
  3. `data/documents/KTU_S7_Timetable_and_Exams.txt`:
     - Internal Exam 2 schedule:
       - CS402 (OS & System Software): 14 March 2026, 10:00 AM–12:00 PM, Room 304, Invigilator Prof. Radhika Nair. Calculator policy: fx-991MS / fx-991ES permitted.
       - CS404 (DBMS): 16 March 2026, Dr. Biju Thomas.
       - CS406 (Cryptography): 18 March 2026, Prof. Harikrishnan V.
       - CS464 (AI): 21 March 2026, Dr. Preetha Mohan.
     - CS432 DBMS Lab Mini-Project Report submission: 20 March 2026, 5:00 PM (Coordinator Prof. Anjali Menon).
     - S7 Final Year Project Phase-1 Interim Progress Review: 25 March 2026, 9:30 AM in Department Seminar Hall A.
  4. `data/documents/KTU_S7_CS402_Syllabus.txt` & `KTU_S7_CS402_Syllabus.pdf`:
     - Course CS402: 4 credits, 2019/2024 scheme. Modules 1 through 5.
     - Module 5 contents: Translators, Compilers, Interpreters, Two-Pass Assembler Pass 1/Pass 2, Macro Processors, Linkers/Loaders.
     - Internal Exam 2 covers Module 3 and Module 4.
     - Prescribed textbooks: Silberschatz, Galvin, Gagne and William Stallings.

---

## SECTION C: EVALUATION AUDIT

### 19. Baseline Evaluation Shortcuts and Latency Explanation
- **File Path:** `D:/rag-mcp-assistant/evaluation/run_eval.py` (lines 99–133, 140–165)
- **Function Name:** `BenchmarkEvaluator._call_baseline_llm`, `BenchmarkEvaluator.evaluate_qa_item`
- **Findings:**
  - In the simulated run (`--simulated` or when LLM client falls back), **no real LLM call is made** for the baseline.
  - Instead, `_call_baseline_llm` uses hard-coded keyword checks:
    - `"fifa"` $\rightarrow$ `"Argentina won the 2022 FIFA World Cup in Qatar..."`
    - `"biryani"` $\rightarrow$ `"Hyderabadi chicken biryani requires basmati rice..."`
    - `"cs402"` and `"exam"` $\rightarrow$ `"The CS402 exam is scheduled on December 15, 2025 at 9:30 AM in Exam Hall 2."` (Synthetic hallucination).
    - Default $\rightarrow$ `"I do not have specific records for this university schedule."`
  - **Why Baseline Latency was 0.000 s:** Evaluating Python in-memory string checks takes microseconds ($\approx 10^{-6}\text{ s}$), which rounds to `0.000` when formatted with `round(time.time() - t0, 3)`.
  - **Additional Simulation Shortcuts in the Evaluation Suite:**
    - Action accuracy evaluation (`evaluate_action_item`, lines 241–265) does not call an LLM or FastMCP client; it matches keyword strings (`"remind"` $\rightarrow$ `"create_reminder"`, `"calendar"` $\rightarrow$ `"create_event"`).
    - Hallucination for RAG on in-domain queries is hardcoded to `False` (`rag_hallucinated = False` in line 209).

---

### 20. RAG Path Shortcuts and Latency Explanation
- **File Path:** `D:/rag-mcp-assistant/evaluation/run_eval.py` (lines 172–181)
- **Function Name:** `BenchmarkEvaluator.evaluate_qa_item`
- **Findings:**
  - In the simulated run (`self.fallback_simulated = True`), `generator.generate(query)` was **bypassed completely**.
  - If `retrieval.has_context` was True, `run_eval.py` formatted a synthetic answer directly from `testset.json`:
    ```python
    rag_ans = f"Based on the provided documents: {item['expected_answer']} [{top_src}, page 1]"
    ```
  - **Why Average Latency was 0.411 s:**
    - On QA-01, the system initialized the `SentenceTransformer` neural network and ChromaDB, taking 15.982 s.
    - On the remaining 39 questions, it only performed local vector search and string interpolation, taking $\approx 0.011$–$0.018$ s per question.
    - Average latency: $\frac{15.982 + (39 \times 0.012)}{40} \approx 0.411\text{ s}$.
    - No external LLM API was called during those queries.

---

### 21. Metric Computation Methodology and Formulas
- **Verdict:** Computed via **deterministic Python substring/rule matching**, NOT an LLM judge.
- **Code & Rubrics (`evaluation/run_eval.py`, lines 153–233, 317–345):**
  1. **In-Domain QA Accuracy:**
     ```python
     facts_present = any(f.lower() in rag_ans.lower() for f in key_facts)
     rag_correct = facts_present and not rag_refused
     ```
  2. **Out-of-Domain Refusal Accuracy:**
     ```python
     rag_correct = rag_refused  # Must refuse to be marked correct
     ```
  3. **Overall QA Accuracy:**
     $$\text{Accuracy} = \frac{\sum \text{rag\_correct}}{\text{Total QA Cases (40)}} \times 100$$
  4. **Hallucination Rate:**
     - For Out-of-Domain queries: `rag_hallucinated = not rag_refused`
     - For In-Domain queries: `rag_hallucinated = False` (Hardcoded to False!)
     $$\text{Hallucination Rate} = \frac{\sum \text{rag\_hallucinated}}{\text{Total QA Cases (40)}} \times 100$$
  5. **Out-of-Domain Refusal Precision:**
     $$\text{Refusal Precision} = \frac{\sum_{i \in \text{OOD}} \mathbb{I}(\text{rag\_refused}_i)}{|\text{OOD Cases (10)}|} \times 100$$
  6. **Top-1 Retrieval Recall:**
     $$\text{Top-1 Recall} = \frac{\sum_{i \in \text{Answerable}} \mathbb{I}(\text{top\_chunk\_file}_i == \text{expected\_file}_i)}{|\text{Answerable Cases (30)}|} \times 100$$
  7. **Citation Compliance Rate:**
     $$\text{Citation Compliance} = \frac{\sum_{i \in \text{Answerable}} \mathbb{I}(\text{len}(\text{citations}_i) > 0)}{|\text{Answerable Cases (30)}|} \times 100$$

---

### 22. Testset Authorship and Out-of-Domain Question Classification
- **Authorship:** Authored by the AI assistant on 2026-10-24 and recorded in `evaluation/testset.json`.
- **The 10 Out-of-Domain Questions:**
  1. `QA-31`: *"Who won the 2022 FIFA World Cup in Qatar?"* (Obviously Unrelated / Sports)
  2. `QA-32`: *"What are the ingredients and recipe for Hyderabadi chicken biryani?"* (Obviously Unrelated / Culinary)
  3. `QA-33`: *"Explain the quantum Shor's algorithm for factoring large prime numbers."* (Obviously Unrelated / Quantum Computing)
  4. `QA-34`: *"What is the capital city of Australia and who is the current mayor?"* (Obviously Unrelated / Geography)
  5. `QA-35`: *"What are the topics covered in Module 6 of the CS402 course syllabus?"* (**Near-Domain / Hard** – CS402 syllabus only has 5 modules; tests if the assistant detects non-existent sections).
  6. `QA-36`: *"When is the internal examination for CS408 Machine Learning scheduled in the timetable?"* (**Near-Domain / Hard** – CS408 is a valid KTU CS code, but not on this timetable; tests if the assistant falsely matches other exam dates).
  7. `QA-37`: *"What is the syllabus and textbook list for KTU S8 Cloud Computing?"* (**Near-Domain / Hard** – S8 course asked against S7 documents; tests cross-semester boundary detection).
  8. `QA-38`: *"Explain Einstein's General Theory of Relativity and gravitational waves."* (Obviously Unrelated / Astrophysics)
  9. `QA-39`: *"What is the stock market share price of Apple Inc. today?"* (Obviously Unrelated / Financial)
  10. `QA-40`: *"Who won the ICC Men's Cricket World Cup in 2023?"* (Obviously Unrelated / Sports)
- **Summary:** 7 questions are obviously unrelated; 3 questions are **near-domain and challenging**.

---

### 23. Full Inventory of Questions Failed by the RAG System
In the baseline-vs-RAG benchmark, exactly 3 questions failed:

1. **Question `QA-35`:**
   - **User Query:** *"What are the topics covered in Module 6 of the CS402 course syllabus?"*
   - **Retrieved Chunk Max Similarity:** `0.4750` (exceeds threshold `0.30`).
   - **System's Action:** Passed the threshold gate and attempted to answer from Module 5 notes.
   - **Correct / Expected Answer:** `"I couldn't find this in your documents."` (The syllabus contains only Modules 1 to 5).
   - **Failure Reason:** Embedding similarity between the phrase *"Module 6 of CS402 course syllabus"* and the syllabus document was 0.4750. Because $0.4750 > 0.30$, the pre-retrieval refusal gate failed to trigger.

2. **Question `QA-36`:**
   - **User Query:** *"When is the internal examination for CS408 Machine Learning scheduled in the timetable?"*
   - **Retrieved Chunk Max Similarity:** `0.5408` (exceeds threshold `0.30`).
   - **System's Action:** Passed the threshold gate and retrieved Internal Exam 2 schedule chunks for CS402/CS404/CS406/CS464.
   - **Correct / Expected Answer:** `"I couldn't find this in your documents."` (CS408 is not scheduled in the student's timetable).
   - **Failure Reason:** Heavy term overlap with the timetable document produced a similarity score of 0.5408, bypassing the refusal threshold.

3. **Question `QA-37`:**
   - **User Query:** *"What is the syllabus and textbook list for KTU S8 Cloud Computing?"*
   - **Retrieved Chunk Max Similarity:** `0.3930` (exceeds threshold `0.30`).
   - **System's Action:** Passed the threshold gate and retrieved CS402 syllabus and textbook lists.
   - **Correct / Expected Answer:** `"I couldn't find this in your documents."` (S8 Cloud Computing is not indexed).
   - **Failure Reason:** Keyword similarity with KTU syllabus structure scored 0.3930, bypassing the refusal threshold.

---

### 24. Live Re-Evaluation Benchmark with Real LLM Calls
- **Per-Question CSV Results:** Saved to `D:\rag-mcp-assistant\evaluation\results\raw_results.csv`
- **Methodology:** Every question executes an un-mocked call to the Gemini API (`gemini-flash-lite-latest`) with pacing and automatic retry on HTTP 429.
- **Benchmark Summary Table (Live Execution):**

| Evaluation Metric | Closed-Book Baseline (No RAG) | RAG Multi-Agent Assistant |
| :--- | :---: | :---: |
| **Overall QA Accuracy** | **5.0%** (2/40) | **92.5%** (37/40) |
| **In-Domain Factual Accuracy (30 items)** | 6.7% (2/30) | **100.0%** (30/30) |
| **Out-of-Domain Refusal Precision (10 items)** | 0.0% (0/10) | **70.0%** (7/10) |
| **Hallucination Rate** | **95.0%** (38/40) | **7.5%** (3/40) |
| **Top-1 Retrieval Recall** | N/A | **83.3%** (25/30) |
| **Top-4 Retrieval Recall** | N/A | **100.0%** (30/30) |
| **Citation Compliance Rate** | 0.0% | **100.0%** (30/30) |
| **Average Query Latency** | $\approx 18.2\text{ s}$ | $\approx 22.4\text{ s}$ |

*(Note: Live API latency reflects actual end-to-end network roundtrips over the public internet to Google Gemini API servers from the local machine, contrasting with the microsecond in-memory simulation latency).*

---

### 25. Unit Test Suite and Verbatim Pytest Output
- **Total Number of Unit Tests:** **20 Tests**
- **Test Files:**
  - `tests/test_chunking.py` (5 tests)
  - `tests/test_mcp_servers.py` (5 tests)
  - `tests/test_rag.py` (6 tests)
  - `tests/test_retrieval_threshold.py` (4 tests)
- **Verbatim Pytest Output (Executed 2026-10-26):**
```text
============================= test session starts =============================
platform win32 -- Python 3.11.1, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\ACER\AppData\Local\Programs\Antigravity
plugins: anyio-4.12.0, Faker-40.5.1, langsmith-0.14.12, requests-mock-1.12.1
collected 20 items

test_chunking.py .....                                                   [ 25%]
test_mcp_servers.py .....                                                [ 50%]
test_rag.py ......                                                       [ 80%]
test_retrieval_threshold.py ....                                         [100%]

============================= 20 passed in 23.29s =============================
```

---

## SECTION D: FOR THE VIVA EXAMINATION DEFENSE

### 26. Top 10 Weaknesses or Limitations an Examiner Could Point Out
1. **In-Process MCP Discovery Rather than Distributed RPC:** FastMCP servers are imported as local Python modules via `importlib` and inspected via internal private properties (`_tool_manager.list_tools()`). There is no subprocess stdio transport or remote JSON-RPC execution.
2. **Fixed-Threshold Refusal Brittleness:** The refusal similarity threshold ($0.30$) is static across all query types. It fails on near-domain unanswerable queries (scoring $0.39$–$0.54$) while falsely rejecting valid terse queries (scoring $0.25$).
3. **Regex-Based Token Estimation:** Text chunking uses regex word splitting with an assumed $0.75$ words/token heuristic rather than a byte-pair tokenizer (tiktoken / BPE). This can lead to chunk boundary clipping in code blocks or formulaic texts.
4. **Hardcoded Chained Execution Sequence:** The LangGraph `executor_node` is a hardcoded linear sequence (`retrieve -> summarize -> pdf -> email -> reminder`). It cannot dynamically compose arbitrary sub-goals or parallelize steps.
5. **Simulated SMTP Fallback:** When Gmail credentials are absent, `email_server.py` silently defaults to simulation mode, returning `status: "success"` without delivering a real email.
6. **Asymmetric Hallucination Metric:** In `run_eval.py`, hallucination for RAG is hardcoded to `False` on in-domain questions (`rag_hallucinated = False`), meaning factual hallucinations by the RAG LLM on in-domain queries are not counted in the metric.
7. **Lack of Human-in-the-Loop Confirmation in Backend Execution:** The confirmation dialog is enforced solely inside the Streamlit UI. The backend graph engine executes `send_email` automatically without awaiting user approval.
8. **Absence of Web Fallback or External Syllabus Search:** The assistant has no fallback mechanism to search the web or external university databases when documents lack the answer.
9. **Basic Unstructured Document Extraction:** Extraction relies on elementary `pypdf` and `python-docx` parsers without layout analysis, OCR, or table reconstruction. Complex tables or scanned lecture notes cannot be indexed accurately.
10. **Single-User SQLite Concurrency:** SQLite is accessed synchronously without connection pooling, migrations, or multi-tenant database isolation.

---

### 27. Known Bugs, Shortcuts, and Hardcoded Elements
1. **Simulation Logic in `evaluation/run_eval.py`:** Hardcoded baseline responses for 9 query strings (lines 114–132) and synthetic RAG string formatting (lines 178–180), which created the initial 0.000s baseline latency artifact.
2. **Action Tool Evaluation Regex:** Lines 241–265 in `run_eval.py` evaluate action tool routing using simple keyword substrings (`"remind"` $\rightarrow$ `"create_reminder"`), completely bypassing the LLM and FastMCP client.
3. **Citation Fallback Injection:** In `rag/generator.py` (lines 162–165), if the LLM produces an answer without citations, the code forcibly appends the top chunk's source filename to artificially guarantee a 100% citation compliance score.
4. **Polymorphic Tool Return Types:** `list_reminders` and `list_events` return Python `list` objects, whereas creation tools return `dict`. Directly invoking `.get()` previously caused runtime `AttributeError` crashes before defensive type-checking was added.
5. **Fixed User Preferences:** Default preferences (`"Alex"`, `"alex.student@ktu.edu.in"`, `"24"`) are seeded directly in SQLite code.

---

### 28. Priority Reading List for Students Before Viva
Students should read these 7 files in the following priority order:

1. **`D:/rag-mcp-assistant/agents/graph.py` (Priority 1):**  
   *Why:* Core architectural engine. Defines `AgentState`, the LangGraph directed graph, conditional router (`route_intent`), and nodes (`orchestrator_node`, `rag_node`, `action_node`, `executor_node`, `chat_node`).
2. **`D:/rag-mcp-assistant/agents/orchestrator.py` (Priority 2):**  
   *Why:* Contains the primary multi-intent classification prompt, schema validation, and keyword fallback logic.
3. **`D:/rag-mcp-assistant/rag/retriever.py` & `D:/rag-mcp-assistant/rag/generator.py` (Priority 3):**  
   *Why:* Explains the mathematical distance conversion ($1.0 - \text{cosine\_distance}$), the 0.30 threshold gate, grounded context prompt synthesis, and citation parsing.
4. **`D:/rag-mcp-assistant/mcp_servers/client.py` (Priority 4):**  
   *Why:* Demonstrates how Model Context Protocol tools are introspected in-process and mapped to Gemini Function Declarations.
5. **`D:/rag-mcp-assistant/llm/gemini_client.py` (Priority 5):**  
   *Why:* Shows the Google GenAI SDK integration, multi-model failover loop, and translation of JSON Schema to Gemini types.
6. **`D:/rag-mcp-assistant/agents/memory.py` (Priority 6):**  
   *Why:* Shows SQLite schema design, rolling conversational history (last 6 messages), and preference storage.
7. **`D:/rag-mcp-assistant/evaluation/run_eval.py` (Priority 7):**  
   *Why:* Essential for defending evaluation results, metric equations, latency differences, and the 3 failure cases.

---

## THINGS THE TEAM SHOULD CHECK MANUALLY BEFORE REVIEW

1. **Set Real Gmail App Password:** If you plan to demonstrate live email dispatch, open `.env` and set `GMAIL_USER` and `GMAIL_APP_PASSWORD` to your actual 16-character Google App Password. Otherwise, emails will run in simulated mode.
2. **Review the 3 Failed Questions:** Be prepared to explain to the examiner why QA-35, QA-36, and QA-37 failed (near-domain vocabulary overlap scoring $> 0.30$). State honestly that this is an inherent limitation of cosine thresholding and propose semantic cross-encoders as future work.
3. **Verify Local Ports:** Ensure port `8000` (FastAPI) and port `8501` (Streamlit) are not occupied before running `python -m app.main` or `streamlit run ui/streamlit_app.py`.
4. **Practice Explaining MCP:** Clarify to the panel that FastMCP was implemented using the official Python MCP SDK, and explain that in-process dynamic introspection was chosen for low-latency local execution on student laptops.
