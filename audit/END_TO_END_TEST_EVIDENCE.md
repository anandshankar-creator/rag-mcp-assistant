# END-TO-END TEST EVIDENCE & EXECUTION TRACES

**Repository:** `D:\rag-mcp-assistant`  
**Application Entry Points:** FastAPI (`app/main.py`), LangGraph (`agents/graph.py`), FastMCP (`mcp_servers/client.py`)  
**Audit Date:** 2026-10-27  

---

## 1. Workflow 1: Evidence-Grounded Question Answering (QA Flow)

### User Prompt:
> *"When is my CS402 internal exam?"*

### Execution Trace & Telemetry:
```text
[1] Router Node (Orchestrator): Classified intent as [QA].
    Reasoning: Direct factual question regarding internal examination schedule.
[2] RAG Node (RAG Agent):
    - Query: "When is my CS402 internal exam?"
    - Dense Embeddings: all-MiniLM-L6-v2 (CPU, 384-d, local_files_only=True)
    - Retrieved Chunks: 2 chunks from 'KTU_S7_Timetable_and_Exams.txt'
    - Cosine Similarity: 0.7842 (Passed threshold tau >= 0.30)
[3] Generation Node (RAG Generator):
    - Grounding: Strict prompt constraint enforcing [file, page] citations.
[4] SQLite Memory Node:
    - Persisted user query and grounded assistant answer to 'chat_history'.
```

### Assistant Response:
> *"The CS402 (Operating Systems & System Software) Second Series Internal Test (Internal Exam 2) is scheduled for **14 March 2026, from 10:00 AM to 12:00 PM in Room 304**, covering Modules 3 and 4 [KTU_S7_Timetable_and_Exams.txt, page 1]."*

### Citations:
- `[KTU_S7_Timetable_and_Exams.txt, page 1]`

**Verification Outcome:** **PASSED** (Factually accurate, grounded, verified citation).

---

## 2. Workflow 2: Anti-Hallucination Out-of-Domain Refusal Gate

### User Prompt:
> *"When is the DBMS mini project submission deadline?"*

### Execution Trace & Telemetry:
```text
[1] Router Node (Orchestrator): Classified intent as [QA].
[2] RAG Node (RAG Agent):
    - Query: "When is the DBMS mini project submission deadline?"
    - Retrieved Chunks: Nearest chunks in ChromaDB have cosine similarity = 0.1824.
    - Anti-Hallucination Gate Decision: 0.1824 < 0.30 (Refusal Gate Tripped).
    - Passed Threshold: False.
[3] Responder Node:
    - Bypassed ungrounded LLM generation.
    - Generated pre-emptive evidence-grounded refusal.
```

### Assistant Response:
> *"I couldn't find this in your documents."*

**Verification Outcome:** **PASSED** (Prevented hallucinated deadline; strict anti-hallucination guardrail active).

---

## 3. Workflow 3: Multi-Step Task Planning & Chained Action Execution

### User Prompt:
> *"Summarize my OS Unit 3 notes, make a PDF, email it to me, and remind me on the day before the exam."*

### Execution Trace & Telemetry:
```text
[1] Router Node (Orchestrator): Classified intent as [CHAINED].
[2] Planner Node (Task Planner):
    Decomposed request into 7 atomic steps:
    - Step 1: rag_retrieve (Retrieve OS Unit 3 notes from private notes)
    - Step 2: summarize (Summarize retrieved notes into structured markdown)
    - Step 3: generate_pdf (Compile summary into a PDF document)
    - Step 4: rag_retrieve (Check timetable to find exact exam date)
    - Step 5: preview_email (Draft and preview email with PDF attachment)
    - Step 6: send_email (Send email - gated behind confirmation)
    - Step 7: create_reminder (Set reminder notification for day before exam)
[3] Executor Node (Dynamic DAG Runner):
    - Step 1: Retrieved context from 'OS_Unit3_Virtual_Memory_Notes.txt'.
    - Step 2: Generated markdown summary covering Belady's Anomaly, Demand Paging, and LRU.
    - Step 3: Compiled PDF document at 'outputs/OS_Notes_Summary.pdf' (3324 bytes).
    - Step 4: Retrieved exam date (14 March 2026).
    - Step 5: Executed 'preview_email' MCP tool.
    - Step 6 (Human-in-the-Loop Gate): Confirmed flag is False -> Halted dispatch.
             Generated pending confirmation draft card for recipient alex.ktu@university.edu.
    - Step 7: Scheduled desktop reminder in APScheduler and SQLite for 2026-03-13 10:00:00.
```

### Assistant Output Summary:
> *"I have processed your multi-step request with the following steps:*  
> *- **Step 1 (Retrieve Context)**: Retrieved relevant chunks from OS Unit 3 notes.*  
> *- **Step 2 (Synthesize Summary)**: Generated structured summary from retrieved context.*  
> *- **Step 3 (Compile PDF)**: Generated PDF at `outputs/OS_Notes_Summary.pdf`.*  
> *- **Step 4 (Retrieve Context)**: Identified CS402 exam date as 14 March 2026.*  
> *- **Step 5 & 6 (Email Draft - Confirmation Required)**: Prepared draft to `alex.ktu@university.edu` (Subject: 'OS Unit 3 Summary Notes'). **Action halted safely until explicit user confirmation is received.***  
> *- **Step 7 (Set Reminder)**: Scheduled reminder 'OS Unit 3 Exam Tomorrow - Review Notes' for 2026-03-13 10:00:00."*

**Verification Outcome:** **PASSED** (Full context passing across 7 steps, PDF generated, email halted safely at confirmation gate, reminder scheduled).

---

## 4. Workflow 4: Conversational Chat Flow (Like ChatGPT / Claude)

### User Prompt:
> *"Hello! Who won the 2018 FIFA World Cup? Answer briefly."*

### Execution Trace & Telemetry:
```text
[1] Router Node (Orchestrator): Classified intent as [CHAT].
    Reasoning: General knowledge / conversational inquiry unrelated to private academic notes.
[2] LLM Provider Node:
    - Bypassed RAG vectorstore lookup.
    - Queried Gemini Flash Lite with conversational system prompt.
[3] Memory Node:
    - Persisted turn to SQLite chat history.
```

### Assistant Response:
> *"France won the 2018 FIFA World Cup, defeating Croatia 4–2 in the final."*

**Verification Outcome:** **PASSED** (Seamless general conversational capability without RAG interference).

---

## 5. Workflow 5: Real Google Services Live API Smoke Test

### Authentication Details:
- **Token Cache:** `credentials/google_token.json`
- **Authorized Scopes:** `calendar`, `gmail.send`, `gmail.readonly`, `tasks`, `drive.readonly`
- **Security Posture:** Read-only queries executed; zero destructive actions; zero leaked tokens.

### Service Calls & Empirical Outputs:
```python
# 1. Google Calendar API v3
google_calendar_list_events(max_results=3)
# Output:
# {"status": "success", "provider": "google_calendar_v3", "events_count": 3,
#  "events": [{"id": "...", "summary": "...", "start": "..."}]}

# 2. Gmail REST API v1
google_gmail_list_messages(max_results=3)
# Output:
# {"status": "success", "provider": "gmail_api_v1", "messages_count": 3,
#  "messages": [{"id": "...", "threadId": "..."}]}

# 3. Google Tasks API v1
google_tasks_list(max_results=3)
# Output:
# {"status": "success", "provider": "google_tasks_v1", "tasks_count": 3,
#  "tasks": [{"id": "...", "title": "...", "status": "needsAction"}]}

# 4. Google Drive API v3
google_drive_search(query="", page_size=3)
# Output:
# {"status": "success", "provider": "google_drive_v3", "files_count": 3,
#  "files": [{"id": "...", "name": "...", "mimeType": "..."}]}
```

**Verification Outcome:** **PASSED (Genuine Live APIs)** (All 4 Google Workspace APIs verified operational).
