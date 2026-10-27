# Actual Software Architecture and Execution Workflows

**Audit Authority:** Source Code Verification of `D:\rag-mcp-assistant`  
**Orchestration Engine:** Compiled LangGraph StateGraph (`agents/graph.py`)  
**Tool Protocol:** Anthropic Model Context Protocol (`mcp.server.fastmcp.FastMCP`)

---

## 1. Architectural Component Inventory

Every component documented below was verified directly from the source code.

```mermaid
flowchart TD
    subgraph ClientLayer ["1. Presentation Layer (ui/streamlit_app.py)"]
        User(["👤 User / Administrator"])
        AdminPortal["🔐 Admin Sign-In & Single-Use Password Reset"]
        ChatInterface["💬 Interactive Chat Interface"]
        HITLCard["⚠️ Human-in-the-Loop Confirmation Card"]
        TelemetryDrawer["📊 Execution Trace & Citation Badges"]
    end

    subgraph SecurityEngine ["2. Authentication & Authorization (app/auth.py)"]
        BcryptModule["Salted Bcrypt Hashing (rounds=12)"]
        LockoutGuard["Progressive Lockout Guard (5 failures -> 15 min lock)"]
        JWTManager["JWT Token Manager & SQLite Revocation Blacklist"]
    end

    subgraph OrchestrationLayer ["3. LangGraph Orchestration State Machine (agents/graph.py)"]
        LoadContextNode["load_context: SQLite History & Preferences"]
        RouterNode["router_node: Intent Classifier (QA | ACTION | CHAINED | CHAT)"]
        PlannerNode["planner_node: JSON Step DAG Decomposition"]
        ExecutorNode["executor_node: Sequential Bounded Step Executor"]
        RAGNode["rag_node: Semantic Retriever & Refusal Gate"]
        ActionNode["action_node: FastMCP Tool Broker"]
        ChatNode["chat_node: Direct Conversational LLM"]
        ResponderNode["responder_node: Grounded Output Synthesizer"]
    end

    subgraph IntelligenceLayer ["4. RAG Core & Web Research Pipeline (rag/)"]
        DocIngest["ingest.py: PDF / DOCX / TXT / MD Parser"]
        TokenChunker["chunking.py: Sliding Window Chunker (~500 tokens, 50 overlap)"]
        LocalEmbedder["embeddings.py: sentence-transformers/all-MiniLM-L6-v2 (384-d)"]
        ChromaStore[("vectorstore.py: ChromaDB (student_knowledge_base)")]
        RefusalGate{"retriever.py: Cosine Gate (max(sim) >= 0.30?)"}
        WebSearchEngine["web_search.py: DuckDuckGo Scraper Engine"]
        DomainRanker["trust_ranker.py: Tier 1 to Tier 4 Domain Authority Scorer"]
        GroundedGen["generator.py: Evidence Synthesizer (Inline Citations)"]
    end

    subgraph ToolMicroservices ["5. FastMCP Tool Ecosystem (mcp_servers/)"]
        MCPClientCtrl["client.py: Dynamic FastMCP Client Controller"]
        ReminderSrv["reminder_server.py: APScheduler + SQLite Reminders"]
        CalendarSrv["calendar_server.py: RFC 5545 .ics Generator"]
        EmailSrv["email_server.py: HITL Preview & SMTP Dispatch"]
        PDFSrv["pdf_server.py: ReportLab Structured PDF Engine"]
        GoogleSrv["google_services_server.py: Google Calendar v3, Gmail v1, Tasks, Drive"]
    end

    subgraph PersistenceLayer ["6. Storage & State Persistence (db/)"]
        SQLiteDB[("db/assistant.db: 10 Relational Tables")]
        FileSystem[("Local Storage: outputs/ & outputs/events/")]
    end

    User --> AdminPortal
    AdminPortal --> SecurityEngine
    SecurityEngine --> ChatInterface
    ChatInterface --> LoadContextNode
    LoadContextNode --> RouterNode

    RouterNode -->|Intent = QA| RAGNode
    RouterNode -->|Intent = ACTION| ActionNode
    RouterNode -->|Intent = CHAINED| PlannerNode
    RouterNode -->|Intent = CHAT| ChatNode

    PlannerNode --> ExecutorNode
    ExecutorNode --> RAGNode
    ExecutorNode --> ActionNode

    RAGNode --> LocalEmbedder
    LocalEmbedder --> ChromaStore
    ChromaStore --> RefusalGate

    RefusalGate -->|sim >= 0.30| GroundedGen
    RefusalGate -->|sim < 0.30 & Web Enabled| WebSearchEngine
    WebSearchEngine --> DomainRanker
    DomainRanker --> GroundedGen

    ActionNode --> MCPClientCtrl
    MCPClientCtrl --> ReminderSrv
    MCPClientCtrl --> CalendarSrv
    MCPClientCtrl --> EmailSrv
    MCPClientCtrl --> PDFSrv
    MCPClientCtrl --> GoogleSrv

    RAGNode --> ResponderNode
    ActionNode --> ResponderNode
    ExecutorNode --> ResponderNode
    ChatNode --> ResponderNode
    ResponderNode --> ChatInterface
```

---

## 2. Request Lifecycles & Flow Descriptions

### 2.1 General Conversational Flow (`CHAT`)
1. User submits an open-ended conversational greeting or conceptual question (e.g., *"Hello! How does your assistant architecture work?"*).
2. `load_context` queries SQLite `chat_history` for the last 6 turns and `user_preferences`.
3. `router_node` (`agents/orchestrator.py`) classifies the intent as `CHAT`.
4. `chat_node` invokes the active LLM provider (Google Gemini Flash Lite) with an instruction prompt restricting it to conversational identity.
5. `responder_node` packages the LLM response, logs the user and assistant turns to `chat_history`, and renders the output in Streamlit.

### 2.2 Local Document Question-Answering Flow (`QA` — Local Document Hit)
```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Streamlit UI
    participant Graph as LangGraph StateMachine
    participant Router as router_node
    participant RAG as rag_node
    participant Retriever as rag.retriever
    participant Chroma as ChromaDB
    participant Gen as rag.generator
    participant LLM as Google Gemini

    User->>UI: Submit question ("What are the CS451 project guidelines?")
    UI->>Graph: run_assistant(user_message)
    Graph->>Router: Classify intent
    Router-->>Graph: route = "QA"
    Graph->>RAG: Execute retrieval
    RAG->>Retriever: retrieve(query, top_k=4)
    Retriever->>Chroma: query(query_embeddings, n_results=4)
    Chroma-->>Retriever: chunks, distances
    Note over Retriever: Calculate sim = 1.0 - distance<br/>Check max(sim) >= 0.30
    Retriever-->>RAG: 4 chunks (peak sim = 0.82 >= 0.30)
    RAG->>Gen: generate_answer(query, chunks)
    Gen->>LLM: Prompt with [file, page] chunks
    LLM-->>Gen: Grounded text + citations
    Gen-->>Graph: Answer with bracketed citations [KTU_S7_Timetable.txt, page 1]
    Graph->>UI: Render response & cite badges
```

### 2.3 Universal Document-First & Web Fallback Flow (`QA` — Local Miss / Web Hit)
```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Router as router_node
    participant RAG as rag_node
    participant Retriever as rag.retriever
    participant Chroma as ChromaDB
    participant Web as rag.web_search
    participant Ranker as rag.trust_ranker
    participant Gen as rag.generator
    participant LLM as Google Gemini

    User->>Router: "When is the next public holiday in Kerala?"
    Router->>RAG: Intent = "QA"
    RAG->>Retriever: Search local ChromaDB
    Retriever->>Chroma: query(query_embeddings)
    Chroma-->>Retriever: Chunks with max(sim) = 0.18 < 0.30
    Note over Retriever: Similarity gate tripped!<br/>Local documents insufficient.
    Retriever-->>RAG: Insufficient local evidence
    RAG->>Web: search_web("public holidays Kerala 2026")
    Web-->>Ranker: Raw DuckDuckGo results
    Ranker-->>Web: Ranked results (Tier 1 .gov / Tier 2 mainstream)
    Web->>Gen: Verified web snippets & URLs
    Gen->>LLM: Synthesize strictly from web evidence
    LLM-->>Gen: Grounded response with live URLs
    Gen-->>User: Answer citing [https://kerala.gov.in/...]
```

### 2.4 MCP Tool Execution Flow (`ACTION` — e.g. Calendar / Reminder)
1. User asks: *"Set a reminder for the CS451 project report submission tomorrow at 5 PM"*.
2. `router_node` classifies intent as `ACTION`.
3. `action_node` (`agents/action_agent.py`) queries `mcp_client.get_tool_definitions()`.
4. LLM parses the natural language date and selects `create_reminder` or `google_calendar_create_event` with structured arguments:
   `{"title": "CS451 project report submission", "due_datetime": "2026-10-28 17:00:00"}`.
5. `mcp_client.execute_tool(tool_name, arguments)` resolves the server function, validates arguments via Python's `inspect.signature()`, and invokes `reminder_server.create_reminder()`.
6. Server writes the record to SQLite `reminders` table and registers an APScheduler background job.
7. `action_node` generates an execution receipt containing status, timestamp, and human-readable confirmation.
8. `responder_node` persists action details to `action_logs` and displays the action confirmation card in the chat UI.

### 2.5 Human-in-the-Loop (HITL) Email Flow (`ACTION` — Email Preview & Dispatch)
```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Streamlit UI
    participant Graph as LangGraph StateMachine
    participant ActionAgent as action_node
    participant MCP as FastMCP email_server

    User->>UI: "Send an email to my project guide submitting the report"
    UI->>Graph: run_assistant(user_message, user_confirmed_actions=False)
    Graph->>ActionAgent: Route = ACTION
    ActionAgent->>MCP: execute_tool("send_email", {"recipient": "...", "confirmed": False})
    Note over MCP: Security Gate:<br/>confirmed == False!
    MCP-->>ActionAgent: status = "requires_confirmation", preview card generated
    ActionAgent-->>Graph: Action suspended pending user review
    Graph-->>UI: Render yellow HITL Confirmation Box (Recipient, Subject, Body)
    Note over User: User inspects preview and clicks "Confirm & Send"
    User->>UI: Click "Confirm & Send"
    UI->>Graph: run_assistant(original_request, user_confirmed_actions=True)
    Graph->>ActionAgent: Dispatch with confirmed = True
    ActionAgent->>MCP: execute_tool("send_email", {"recipient": "...", "confirmed": True})
    MCP-->>ActionAgent: status = "success", message_id = "..."
    ActionAgent-->>UI: Green Confirmation: "Email dispatched successfully"
```

### 2.6 ReportLab PDF Generation and Secure Download Flow
1. User submits: *"Generate a PDF report summarizing Operating Systems Virtual Memory notes"*.
2. `router_node` routes request to `planner_node` (`CHAINED` intent).
3. `planner_node` creates a 2-step DAG:
   - Step 1: `rag_search` for *"Operating Systems Virtual Memory"*
   - Step 2: `generate_pdf` passing the retrieved text
4. `executor_node` executes Step 1, extracts summary text, and passes it to Step 2.
5. FastMCP `pdf_server.generate_pdf(title, content, filename)` formats document styles, compiles the PDF via ReportLab, generates a SHA-256 integrity hash, and writes the binary to `outputs/CS402_Module3_Revision.pdf`.
6. In `ui/streamlit_app.py`, the assistant detects the `.pdf` path in the action receipt.
7. The UI renders an inline `st.download_button()` allowing the authenticated administrator to download the compiled PDF directly from chat without unauthenticated file exposure.

---

## 3. Decision Logic & Universal Routing Engine

The system uses a deterministic, rule-informed decision pipeline implemented in `agents/orchestrator.py` and `rag/generator.py`:

```
User Query Received
       │
       ▼
Is it a Profile Query? (e.g. "what's my email") ──► YES ──► Answer from user_preferences table
       │ NO
       ▼
Is it an Action Follow-up? (e.g. "how did you send that?") ──► YES ──► Inspect action_logs table
       │ NO
       ▼
LLM Few-Shot Intent Classification
       ├─► CHAT ──────► Direct Conversational LLM Response
       ├─► ACTION ────► Action Agent (FastMCP Dynamic Tool Invocation)
       ├─► CHAINED ───► Planner Node (Step DAG Decomposition & Execution)
       └─► QA ────────► Universal Document-First Evaluation
                             │
                             ▼
                   Local ChromaDB Search (top_k=4)
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
      max(sim) >= 0.30                  max(sim) < 0.30
            │                                 │
   Evaluate Relevance                 Web Fallback Enabled?
   of Retrieved Chunks                        │
     ┌──────┴──────┐                   ┌──────┴──────┐
     ▼             ▼                   ▼             ▼
  Complete      Partial               YES            NO
   Answer        Evidence              │             │
     │             │                   ▼             ▼
  Answer         Fill Gap        DuckDuckGo     Refuse Grounded:
  From Docs      via Web          Web Search     "I couldn't find
  [file, page]   [file, page]          │          this in documents"
                   + [URL]       Domain Trust
                                    Ranking
                                 (Tier 1 / 2)
                                       │
                                ┌──────┴──────┐
                                ▼             ▼
                             Evidence     No Reliable
                              Found         Sources
                                │             │
                             Answer        Honest
                            With URLs    Uncertainty
                                          Refusal
```
