# IDEA MATCH REPORT: AUDIT OF PROJECT GOALS VS IMPLEMENTED CODEBASE

**Project Title:** A Retrieval-Augmented Generation Based Multi-Agent Personal Assistant Architecture Using the Model Context Protocol (MCP)  
**Target Repository:** `D:\rag-mcp-assistant`  
**Audit Date:** 2026-10-26  
**Auditor:** Automated Codebase & Repository Integrity Verification Suite  

---

## EXECUTIVE SUMMARY: PROJECT GOALS COMPLIANCE (G1 TO G6)

| Goal | Description | Status | Primary Code Files & Functions | Plain Description of Actual Code Behavior |
| :--- | :--- | :---: | :--- | :--- |
| **G1** | Local RAG over user's documents with citations and refusal when absent | **IMPLEMENTED** | `rag/retriever.py` (`Retriever.retrieve`), `rag/generator.py` (`RAGGenerator.answer_question`), `rag/vectorstore.py` (`VectorStoreManager`) | Chunks PDF/TXT/DOCX/MD files, embeds with `all-MiniLM-L6-v2` into local ChromaDB. If max cosine similarity $< 0.30$, immediately returns *"I couldn't find this in your documents."* without calling LLM. If $\ge 0.30$, prompts LLM with strict context constraints and extracts `[filename, page]` citations. |
| **G2** | Internet fallback when local documents do not contain the answer | **NOT IMPLEMENTED** | `rag/generator.py` (lines 123–134), `agents/graph.py` (`rag_node`) | When local retrieval similarity falls below 0.30 (`has_context = False`), the system returns the hardcoded refusal string. There is no web search API, no HTTP scraping client, and no routing branch to any web query service. |
| **G3** | Web answers use only TRUSTED sources via trust ranking | **NOT IMPLEMENTED** | *None* | No search engine integration (DuckDuckGo, SerpAPI, Tavily, Google Search), no trusted domain whitelist (e.g. `.edu`, `.gov`), no domain authority scoring, and no reputation filtering logic exists anywhere in the codebase. |
| **G4** | Web answers grounded in fetched text, cite URLs, and are verified | **NOT IMPLEMENTED** | *None* | No HTML fetching libraries (`requests`, `httpx`, `BeautifulSoup`, `trafilatura`), no URL citation parsing, and no quote-verification matching logic exists. |
| **G5** | MCP integration with Google services (Calendar, Gmail, Drive, Tasks, Keep, Alarms) | **PARTLY** | `mcp_servers/calendar_server.py`, `mcp_servers/email_server.py`, `mcp_servers/reminder_server.py`, `mcp_servers/client.py` | 4 FastMCP servers exist, but they are **local implementations or standard SMTP**, NOT Google API integrations. Calendar uses local SQLite + `.ics` files; Email uses standard Gmail SMTP with an App Password (or simulated mode); Reminders use local SQLite + `APScheduler` + `plyer` desktop alerts. Drive, Google Tasks, and Google Keep are **NOT IMPLEMENTED**. No Google OAuth 2.0 flow exists. |
| **G6** | Measurably reduces hallucination vs plain LLM, including on non-local queries | **PARTLY** | `evaluation/run_eval.py`, `evaluation/testset.json`, `evaluation/results/` | Evaluates local RAG vs Closed-Book Baseline across 40 questions (30 in-domain, 10 out-of-domain). Shows RAG refusal on 7/10 out-of-domain queries where the baseline hallucinated. However, it does not evaluate any web fallback (since none exists), uses simulation shortcuts in `run_eval.py`, and hardcodes in-domain RAG hallucination to `False`. |

---

## SECTION A: LOCAL TO WEB FALLBACK (G2 TO G4)

### 1. Behavior when Local Retrieval Falls Below Threshold
- **Code Path:**
  1. `rag/retriever.py` (`Retriever.retrieve`, lines 103–120):
     ```python
     passed_chunks = [c for c in candidate_chunks if c.similarity >= threshold]
     if not passed_chunks:
         return RetrievalResult(chunks=[], max_similarity=max_sim, passed_threshold=False, has_context=False)
     ```
  2. `rag/generator.py` (`RAGGenerator.answer_question`, lines 123–134):
     ```python
     if not retrieval.has_context:
         refusal_message = "I couldn't find this in your documents."
         return RAGResponse(
             query=query,
             answer=refusal_message,
             citations=[],
             retrieved_chunks=trace_chunks,
             refused=True,
             max_similarity=retrieval.max_similarity,
         )
     ```
  3. `agents/graph.py` (`rag_node`, lines 170–195):
     The refusal message is assigned to `state["response"]`, and graph execution routes to `END`.
- **Is there any web search or fetch tool at all?** **NO (NOT IMPLEMENTED)**.
- **Which library or API (free or paid)?** **NONE**. There is no dependency on `requests`, `urllib` (for web search), `duckduckgo-search`, `tavily-python`, `googlesearch-python`, `beautifulsoup4`, or `newspaper3k`.

---

### 2. Search Result Ranking and Domain Filtering
- **Status:** **NONE / NOT IMPLEMENTED**
- **Evidence:**
  - There is no search result ranking function in the codebase.
  - There is no whitelist of trusted domains (e.g. `.edu`, `.gov`, `.ac.in`, `wikipedia.org`).
  - There is no domain tiering (Tier 1 Academic, Tier 2 Media, Tier 3 Blogs) or mathematical trust score formula.

---

### 3. Guardrails Against LLM Parametric Memory on Web Path
- **Status:** **NOT APPLICABLE / NOT IMPLEMENTED** (No web path exists).
- **Local RAG Guardrail:** On the local RAG path, memory leakage is prevented by `RAG_SYSTEM_PROMPT` in `rag/generator.py` (lines 45–51):
```text
You are a strict academic personal assistant for a university student.
Your instructions are mandatory:
1. Answer ONLY from the provided context chunks below.
2. If the context does not contain the answer, say "I couldn't find this in your documents."
3. Cite sources for every claim as [filename, page] (e.g. [OS_Unit3_Virtual_Memory_Notes.txt, page 1]).
4. Do not use outside knowledge or extrapolate beyond the provided text.
5. Be concise, direct, and factually precise.
```
- For web search answers, no prompt or guardrail exists because no web synthesis module is implemented.

---

### 4. URL Citations and Quote Verification
- **Status:** **NOT IMPLEMENTED**
- **Evidence:**
  - Citation extraction in `rag/generator.py` (`extract_citations`, lines 68–83) uses regex pattern `r"\[([a-zA-Z0-9_\-\.]+(?:\.[a-zA-Z0-9]+)?),\s*(?:page|p\.)?\s*(\d+)\]"`. It only extracts local file citations formatted as `[filename, page]`.
  - There is no URL regex pattern, no URL validator, and no verification function in code to cross-reference extracted quotes against fetched HTML text.

---

### 5. Handling Source Disagreements and Absent Trusted Sources
- **Status:** **NOT IMPLEMENTED**
- **Evidence:**
  - For local RAG, if multiple retrieved chunks contain conflicting information, all top-$k$ chunks are concatenated into the prompt, leaving resolution entirely up to the non-deterministic LLM.
  - For web retrieval, neither source disagreement resolution nor absence-of-trusted-source handling exists.

---

### 6. Untrusted Web Data and Prompt Injection Protection
- **Status:** **NOT IMPLEMENTED (No web pages are fetched)**
- **Local Document Injection Defense Analysis:**
  - Local document chunks are interpolated directly into the user prompt (`CONTEXT DOCUMENTS:\n{context_text}\n\nSTUDENT QUESTION:\n{query}`) without XML boundary tagging or sanitization against prompt injection.
  - **Tool Execution Isolation:** In the QA route (`rag_node`), tool declarations are **not passed** to `self.llm_client.generate()`. Therefore, adversarial text inside a document cannot trigger `send_email` or any other tool during a QA query. Tool calling is strictly isolated to `action_node`.

---

### 7. Origin Labeling of Answers (Local / Web / Not Found)
- **Status:** **PARTLY IMPLEMENTED**
- **File Path:** `app/main.py` (`ChatResponse`), `ui/streamlit_app.py`
- **What is Implemented:**
  - The API response contains `route` (`"QA"`, `"ACTION"`, `"CHAINED"`, `"CHAT"`) and `citations` (e.g. `["OS_Unit3_Virtual_Memory_Notes.txt, page 1"]`).
  - If refused, the response explicitly says `"I couldn't find this in your documents."`.
  - The Streamlit UI displays a "Sources Cited" expander when citations exist.
- **What is Missing:**
  - There is **no `"web"` origin label**, because web retrieval does not exist. The system only differentiates between answered from local documents vs refused ("not found").

---

## SECTION B: GOOGLE MCP SERVICES (G5)

### 8. Complete Inventory of MCP Servers and Tools
The repository implements 4 FastMCP servers in `mcp_servers/`:

| MCP Server File | Tool Name | Parameters | Return Schema / Value |
| :--- | :--- | :--- | :--- |
| `mcp_servers/reminder_server.py` | `create_reminder` | `title: str`, `due_datetime: str`, `note: str = ""` | `{"status": "success", "reminder": {"id": int, "title": str, "due_datetime": str, "note": str}}` |
| `mcp_servers/reminder_server.py` | `list_reminders` | None | `List[Dict[str, Any]]` (All active reminders from SQLite) |
| `mcp_servers/reminder_server.py` | `delete_reminder` | `reminder_id: int` | `{"status": "success", "deleted_id": int}` |
| `mcp_servers/calendar_server.py` | `create_event` | `title: str`, `start_datetime: str`, `end_datetime: str`, `attendees: str = ""`, `description: str = ""` | `{"status": "success", "event": {"id": int, "title": str, ...}, "ics_file": str}` |
| `mcp_servers/calendar_server.py` | `list_events` | None | `List[Dict[str, Any]]` (All events from SQLite) |
| `mcp_servers/calendar_server.py` | `delete_event` | `event_id: int` | `{"status": "success", "deleted_id": int}` |
| `mcp_servers/email_server.py` | `preview_email` | `to: str`, `subject: str`, `body: str`, `attachment_path: str = ""` | `{"status": "preview", "to": str, "subject": str, "body": str, "attachment_path": str, "ready_to_send": True}` |
| `mcp_servers/email_server.py` | `send_email` | `to: str`, `subject: str`, `body: str`, `attachment_path: str = ""`, `confirmed: bool = True` | `{"status": "success", "mode": "simulated"\|"smtp", "to": str, "subject": str}` or `{"status": "error", "message": str}` |
| `mcp_servers/pdf_server.py` | `generate_pdf` | `title: str`, `content: str`, `filename: str = ""` | `{"status": "success", "pdf_path": str, "filename": str, "size_bytes": int}` |

---

### 9. Google Service Status Breakdown

| Google Service | Actual Implementation Level | Code Evidence & Mechanism |
| :--- | :---: | :--- |
| **Google Calendar** | **LOCAL** | Uses SQLite table `calendar_events` in `db/assistant.db` + local `.ics` file generation via Python `ics` library (`mcp_servers/calendar_server.py`). **Does NOT call Google Calendar API.** |
| **Gmail** | **LOCAL / SIMULATED** | Uses standard Python `smtplib.SMTP` over port 587 with a Gmail App Password (`mcp_servers/email_server.py`). If credentials are not set, runs in **SIMULATED** mode. **Does NOT call Google Gmail REST API.** |
| **Google Drive** | **NOT IMPLEMENTED** | No code, server, or file references exist for Google Drive. Documents are read solely from local disk (`data/documents/` and `outputs/`). |
| **Google Tasks** | **NOT IMPLEMENTED** | No integration with Google Tasks API. Reminders are stored in a local SQLite table (`reminders`). |
| **Google Keep** | **NOT IMPLEMENTED** | No code or server exists for Google Keep notes. |
| **Google Alarms / Reminders** | **LOCAL** | Uses SQLite `reminders` table + in-memory `APScheduler` background scheduler + local desktop notifications via Python `plyer.notification` (`mcp_servers/reminder_server.py`). **Does NOT interface with Google Clock / Alarms.** |

---

### 10. Google Authentication Architecture
- **Status:** **NOT IMPLEMENTED**
- **Evidence:**
  - There is no Google OAuth 2.0 implementation anywhere in the codebase.
  - No `google-auth`, `google-auth-oauthlib`, or `google-api-python-client` libraries are used.
  - No OAuth client ID, client secret, redirect URI, authorization code flow, or token storage (`token.json` / `credentials.json`) exists.
  - The only Google-related authentication is a static 16-character SMTP App Password (`GMAIL_APP_PASSWORD` in `.env`) for sending emails via standard SMTP.

---

### 11. Actions Requiring User Confirmation Before Execution
- **File Path:** `ui/streamlit_app.py` (lines 280–330), `mcp_servers/email_server.py` (lines 75–100), `agents/graph.py` (lines 295–325)
- **Detailed Enforcement:**
  - **In Streamlit UI:** **Only `send_email`** requires explicit user confirmation. The Action Agent first returns a `preview_email` receipt, and the UI renders an interactive card showing the recipient, subject, and body with a "Confirm & Send" button.
  - **All other actions execute autonomously:** `create_reminder`, `delete_reminder`, `create_event`, `delete_event`, and `generate_pdf` run immediately without human confirmation.
  - **In Backend LangGraph (`agents/graph.py`):** In the chained pipeline (`executor_node`), `send_email` is called directly with `confirmed=True` without pausing for user intervention.

---

## SECTION C: HALLUCINATION EVIDENCE (G6)

### 12. Evaluation Configurations and Out-of-Domain Test Sets
- **Configurations That Exist:**
  1. `Closed-Book Baseline` (Plain LLM without document context).
  2. `Local RAG` (ChromaDB context-grounded LLM generation).
  - *`RAG plus Web`:* **DOES NOT EXIST / NOT IMPLEMENTED**.
- **Test Set Composition (`evaluation/testset.json`):**
  - Total: 40 QA cases + 10 Action cases.
  - In-Domain Answerable: 30 questions (Operating Systems, DBMS, Timetable, Syllabus).
  - Out-of-Domain Questions: Exactly **10 questions** (QA-31 to QA-40):
    - 7 are general knowledge web-answerable: FIFA World Cup 2022 (QA-31), Biryani recipe (QA-32), Shor's algorithm (QA-33), Capital of Australia (QA-34), General Relativity (QA-38), Apple stock price (QA-39), Cricket World Cup 2023 (QA-40).
    - 3 are near-domain curriculum trick questions: Module 6 of CS402 (QA-35), CS408 exam timetable (QA-36), S8 Cloud Computing (QA-37).
  - **Authorship:** All questions, key facts, and ground-truth answers were authored by the AI assistant on 2026-10-24.

---

### 13. Audit of `evaluation/run_eval.py` (Mocking, Caching, and Latency)
- **File Path:** `D:/rag-mcp-assistant/evaluation/run_eval.py`
- **Findings:**
  - **Baseline Path (`_call_baseline_llm`, lines 114–132):**
    When run with `--simulated` or when the LLM client falls back, **no LLM call is made**. The baseline returns hardcoded strings matching query keywords:
    ```python
    if "fifa" in query.lower():
        return "Argentina won the 2022 FIFA World Cup in Qatar, defeating France in the final."
    if "cs402" in query.lower() and "exam" in query.lower():
        return "The CS402 exam is scheduled on December 15, 2025 at 9:30 AM in Exam Hall 2." # Synthetic hallucination
    ```
    *Why baseline latency was 0.000 s:* In-memory string matching in Python runs in microseconds, rounding to `0.000 s`.
  - **RAG Path (`evaluate_qa_item`, lines 172–181):**
    When `fallback_simulated = True`, the LLM was **not called**. If retrieval succeeded, it formatted synthetic answers directly from `testset.json`:
    ```python
    rag_ans = f"Based on the provided documents: {item['expected_answer']} [{top_src}, page 1]"
    ```
  - **Action Evaluation (`evaluate_action_item`, lines 241–265):**
    Completely simulated via simple string matching (`if "remind" in q_lower...`), bypassing LLMs and MCP clients.

---

### 14. Hallucination and Accuracy Scoring Methodology
- **Verdict:** Computed via **deterministic Python substring rules**, NOT an LLM judge.
- **Code Rubric (`evaluation/run_eval.py`, lines 153–210):**
  1. **In-Domain Questions:**
     ```python
     facts_present = any(f.lower() in rag_ans.lower() for f in key_facts)
     rag_correct = facts_present and not rag_refused
     rag_hallucinated = False  # Hardcoded to False for RAG!
     ```
     *(Critical Finding: For in-domain questions, RAG hallucination is hardcoded to `False`. Any factual distortion or hallucination produced by RAG on in-domain documents is mathematically excluded from the hallucination metric).*
  2. **Out-of-Domain Questions:**
     ```python
     if should_refuse:
         rag_correct = rag_refused
         rag_hallucinated = not rag_refused
     ```
  3. **Baseline Scoring:**
     ```python
     if should_refuse:
         base_hallucinated = not base_refused  # Answering OOD query = hallucination
         base_correct = False
     else:
         has_private_facts = any(f.lower() in base_ans.lower() for f in key_facts)
         base_correct = has_private_facts
         base_hallucinated = not base_correct and not base_refused
     ```

---

### 15. Cases the System Answered Wrongly or Without Support
In the evaluation benchmark, exactly **3 questions failed** (all due to near-domain threshold leakage):

1. **`QA-35`:**
   - **Query:** *"What are the topics covered in Module 6 of the CS402 course syllabus?"*
   - **Retrieved Chunk Max Similarity:** `0.4750` ($> 0.30$).
   - **System Answer:** Attempted to answer from Module 5 chunks instead of refusing.
   - **Expected Answer:** `"I couldn't find this in your documents."` (Syllabus only has Modules 1 to 5).
2. **`QA-36`:**
   - **Query:** *"When is the internal examination for CS408 Machine Learning scheduled in the timetable?"*
   - **Retrieved Chunk Max Similarity:** `0.5408` ($> 0.30$).
   - **System Answer:** Retrieved chunks for other exams (CS402, CS404, CS406) and attempted to answer.
   - **Expected Answer:** `"I couldn't find this in your documents."` (CS408 is absent from the timetable).
3. **`QA-37`:**
   - **Query:** *"What is the syllabus and textbook list for KTU S8 Cloud Computing?"*
   - **Retrieved Chunk Max Similarity:** `0.3930` ($> 0.30$).
   - **System Answer:** Retrieved CS402 syllabus chunks and attempted to answer.
   - **Expected Answer:** `"I couldn't find this in your documents."` (S8 Cloud Computing is not in the knowledge base).

---

### 16. Testing Web Path Against Plain LLM with Generic Search
- **Status:** **NOT TESTED**
- **Evidence:** The web search path does not exist in the codebase. No comparative benchmark between local RAG, web-augmented RAG, and plain LLM with web search was ever executed.

---

## SECTION D: GAP LIST AND REMEDIATION ROADMAP

### 17. Comprehensive Gap Matrix

| Project Goal | Current Codebase Status | What is Missing | Estimated Effort | Files Requiring Changes |
| :--- | :---: | :--- | :---: | :--- |
| **G1: Local RAG with Citations & Refusal** | **IMPLEMENTED** | Dynamic cross-encoder re-ranking to prevent near-domain leakage (QA-35, 36, 37); real tokenizer replacing regex approximation. | **Small** (1–2 days) | `rag/retriever.py`, `rag/chunking.py`, `rag/generator.py` |
| **G2: Local to Web Fallback** | **NOT IMPLEMENTED** | Web search API client (e.g. DuckDuckGo / Tavily); HTML text extraction (`trafilatura` / `BeautifulSoup`); fallback routing branch in LangGraph when local retrieval fails. | **Medium** (3–4 days) | `rag/web_search.py` (new), `agents/graph.py`, `rag/generator.py`, `app/config.py` |
| **G3: Trusted Source Ranking** | **NOT IMPLEMENTED** | Whitelist of trusted academic/government domains; domain authority scoring function; filtering out unverified blogs and forums. | **Medium** (2–3 days) | `rag/trust_ranker.py` (new), `rag/web_search.py`, `app/config.py` |
| **G4: Grounded Web Synthesis & Verification** | **NOT IMPLEMENTED** | Web-specific grounding system prompt; URL citation regex parser; quote-verification algorithm checking LLM statements against scraped HTML. | **Medium** (3–4 days) | `rag/generator.py`, `rag/retriever.py`, `ui/streamlit_app.py` |
| **G5: Google Services MCP Integration** | **PARTLY** (Local SQLite/SMTP only) | Google OAuth 2.0 flow; official Google Calendar API, Gmail REST API, Google Drive API, Google Tasks API, and Google Keep API clients; replacing local `.ics` and SQLite stubs. | **Large** (1–2 weeks) | `mcp_servers/google_auth.py` (new), `mcp_servers/calendar_server.py`, `mcp_servers/email_server.py`, `mcp_servers/drive_server.py` (new), `mcp_servers/tasks_server.py` (new) |
| **G6: Measurable Hallucination Reduction (Local + Web)** | **PARTLY** (Local RAG only) | Dedicated benchmark testset for web-grounded queries; removing simulation shortcuts from `run_eval.py`; replacing substring matching with an LLM judge. | **Medium** (3–4 days) | `evaluation/run_eval.py`, `evaluation/testset.json`, `evaluation/evaluator.py` |

---

### 18. Five Most Serious Risks for the Examination Review

1. **Misrepresenting Local SQLite/SMTP Stubs as "Google Integration":**  
   If the report or presentation claims the assistant connects to "Google Calendar, Gmail, Google Drive, Google Tasks, and Google Keep", an examiner inspecting the repository will immediately find that Drive, Tasks, and Keep do not exist, Calendar is a local SQLite table generating `.ics` files, and Gmail is standard SMTP using an App Password (or simulated mode), with zero Google OAuth or Google Cloud API dependencies.
2. **Claiming Internet Fallback and Trusted Domain Ranking When Web Search Does Not Exist:**  
   If slides claim the system searches the internet for answers missing from notes, examiners will discover that `rag/generator.py` lines 123–134 strictly return *"I couldn't find this in your documents."* without performing any network search or domain authority filtering.
3. **Simulation Artifacts in `evaluation/run_eval.py`:**  
   The baseline evaluation function `_call_baseline_llm` uses hardcoded `if/elif` string checks (producing the unrealistic 0.000 s latency), and `evaluate_qa_item` formatted synthetic answers directly from `testset.json` during simulated runs. An examiner reviewing code will recognize this as mocked data rather than real LLM inference.
4. **Hardcoded Zero Hallucination for In-Domain RAG:**  
   Line 209 of `evaluation/run_eval.py` sets `rag_hallucinated = False` for all in-domain questions. This means that if RAG synthesizes factually distorted or ungrounded answers on private notes, the metric mathematically ignores it.
5. **Overfitted Static Refusal Threshold (0.30):**  
   The refusal similarity threshold of 0.30 was hand-tuned on the 40 test queries. It creates a critical vulnerability where near-domain unanswerable queries (e.g. asking for non-existent Module 6) score 0.475 and bypass refusal, while valid terse questions (e.g. *"What is Belady's Anomaly?"*) score 0.25 and get rejected.

---

## THINGS THE TEAM MUST VERIFY MANUALLY BEFORE THE REVIEW

1. **Align Presentation Slides with Actual Code:** Do NOT claim Google Drive, Google Tasks, Google Keep, or Web Search are implemented. Present the current project accurately as a **"Local-First Grounded RAG Assistant with FastMCP Local Tool Automation (Calendar, Email, Reminders, PDF)"**.
2. **Explain FastMCP In-Process Architecture Honestly:** State clearly that MCP tools are implemented using the official FastMCP Python SDK in-process to minimize latency on student laptops, rather than claiming a distributed multi-node MCP network.
3. **Be Prepared to Defend the 3 Evaluation Failures:** If asked about QA-35, QA-36, and QA-37, explain that vocabulary overlap between syllabus modules creates cosine similarity above 0.30, and cite cross-encoder re-ranking as the planned solution.
4. **Demonstrate Real Email Dispatch Carefully:** If demonstrating live email sending, ensure a valid 16-character Google App Password is placed in `.env`. Otherwise, explain to the panel that the system operates in simulated mode to protect credentials during evaluation.
5. **Acknowledge the Web Fallback as Future Work:** Frame the Local-to-Internet Fallback and Trusted Source Ranking (G2–G4) as the designated Phase 2 extension for the final semester review.
