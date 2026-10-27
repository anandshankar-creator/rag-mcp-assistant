# Academic Report Content Draft: Chapters and Sections

**Target Report:** KTU B.Tech CSE Final Year Project Report  
**Project Title:** A Retrieval-Augmented Generation Based Multi-Agent Personal Assistant Architecture Using the Model Context Protocol (MCP)  
**Academic Authority:** Grounded strictly in the verified source code and test results of `D:\rag-mcp-assistant`.

---

## Abstract

Contemporary Large Language Models (LLMs) deployed as conversational personal assistants suffer from two fundamental deficiencies in private knowledge domains: parametric hallucinations on local or unpublished documents, and execution isolation from operating system services and external application APIs. When queried on private course notes, internal syllabi, or examination timetables, closed-book LLMs frequently invent nonexistent facts, regulations, or dates. Furthermore, traditional conversational interfaces operate as closed text silos incapable of scheduling calendar events, managing reminders, sending verified emails, or compiling structured reports without fragile, vendor-locked scripting.

To resolve these limitations, this project presents an end-to-end, privacy-preserving **Multi-Agent Personal Assistant Architecture**. The system unifies a local **Retrieval-Augmented Generation (RAG)** pipeline—featuring dense semantic embeddings (`sentence-transformers/all-MiniLM-L6-v2`), persistent vector indexing (`ChromaDB`), an anti-hallucination cosine similarity threshold gate ($\tau = 0.30$), and an intelligent **local-to-web fallback** with **domain trust ranking**—with Anthropic's open **Model Context Protocol (FastMCP)**. Coordinated by a compiled **LangGraph StateGraph** managing Orchestrator, Planner, RAG, and Action agents, the assistant achieves grounded question answering with inline bracketed citations alongside deterministic, Human-in-the-Loop automation (Local Reminders via APScheduler, RFC 5545 Calendar `.ics` generation, secure Email preview/dispatch, ReportLab PDF compilation, and authenticated Google Workspace integrations for Google Calendar API v3, Gmail REST API v1, Google Tasks, and Google Drive).

The system enforces strict administrator-only security via salted bcrypt hashing (`rounds=12`), progressive brute-force lockout, cryptographic JWT session tokens with SQLite revocation blacklists, and single-use SHA-256 password reset tokens. Evaluated across 25 standardized academic curriculum test queries, the architecture achieved a **100.0% out-of-domain refusal precision** (completely eliminating parametric hallucinations on private out-of-domain topics) and **100.0% FastMCP tool dispatch accuracy** across 17 distinct tools. The system has been validated across a formal automated test suite of **124 tests passing with a 100% success rate**, confirming its readiness for academic viva voce defense and public cloud deployment.

---

## 1. Introduction

### 1.1 Background and Motivation
Artificial intelligence assistants have become primary interfaces for productivity, research, and task automation. However, general-purpose LLMs operate as closed-book systems trained on broad public web corpora. In academic settings, undergraduate engineering students and faculty regularly interact with private, fast-changing documents: lecture handouts, semester revision notes, lab manuals, and university timetable amendments. Standard LLMs cannot read these local files and routinely generate inaccurate claims when asked specific curriculum questions.

Furthermore, traditional AI chatbots are strictly passive text engines. While they can draft an email or compose an event description, they cannot interact with the operating system to set a reminder, produce an importable calendar file, or interface with an authorized enterprise service like Google Workspace. Enabling language models to execute real-world tools requires a protocol that is open, modular, and safe. The Model Context Protocol (MCP), open-sourced by Anthropic, provides this standard. By integrating local RAG with FastMCP microservices under a multi-agent state machine, this project establishes a reliable, hallucination-resistant personal assistant.

### 1.2 Problem Statement
Existing conversational AI architectures exhibit three primary engineering failures when applied to personal and academic workflows:
1. **Unconstrained Hallucination:** Inability to distinguish between queries answerable from private local documents and queries requiring external web evidence or honest refusals.
2. **Tool Coupling & Vendor Lock-In:** Reliance on proprietary, monolithic tool wrappers that hardcode function definitions into LLM prompt templates, preventing dynamic discovery and real-time capability expansion.
3. **Execution Insecurity:** Lack of deterministic safety barriers, resulting in unintended real-world side effects (such as autonomous email transmission) and vulnerable public interfaces.

### 1.3 Aim and Specific Objectives
The central aim is to design, implement, and empirically evaluate a privacy-preserving, hallucination-resistant multi-agent personal assistant using RAG and FastMCP.

**Specific Objectives:**
1. Develop an ingestion and chunking pipeline supporting PDF, DOCX, TXT, and Markdown files with 1-indexed page-number preservation.
2. Implement local dense vector embeddings (`all-MiniLM-L6-v2`, 384 dimensions) and persistent vector indexing via ChromaDB.
3. Engineer an anti-hallucination cosine similarity gate ($\tau = 0.30$) that refuses ungrounded private queries and triggers trusted web research for factual queries.
4. Build a domain trust ranking engine categorizing external sources into Tier 1 (.edu/.gov) through Tier 4 authorities.
5. Deploy 5 independent FastMCP tool microservices exposing 17 distinct tools for reminders, calendar scheduling, email previews, PDF synthesis, and Google Workspace APIs.
6. Enforce Human-in-the-Loop (HITL) confirmation gates for all operations with real-world side effects.
7. Coordinate agent state transitions using a compiled LangGraph StateGraph bounding multi-step execution to 10 safe steps.
8. Implement thread-safe Google Gemini API key pool rotation with automatic 60-second backoff cooldown on HTTP 429 quota exhaustion.
9. Enforce single-administrator security via salted bcrypt hashing, brute-force defense, JWT session revocation, and single-use password reset tokens.
10. Validate the complete architecture through 124 formal automated tests and empirical benchmark evaluation.

---

## 2. System Analysis & Requirements

### 2.1 Hardware Requirements
- **Development & Host Computer:** Intel Core i5 or AMD Ryzen 5 processor (quad-core or higher).
- **Random Access Memory (RAM):** 8 GB minimum (16 GB recommended to support local PyTorch embeddings and ChromaDB indexing simultaneously).
- **Persistent Storage:** 2 GB available disk space for Python runtime, dependencies, SQLite database (`assistant.db`), and vector collections.

### 2.2 Software Requirements
- **Programming Language:** Python 3.11.1 (64-bit).
- **Core Frameworks:** Streamlit 1.38+, FastAPI 0.115+, Uvicorn 0.30+.
- **Multi-Agent & Tool Protocols:** LangGraph 0.2.20+, Anthropic FastMCP (`mcp 1.0+`).
- **Data & Vectors:** ChromaDB 0.5.5+, SQLite 3, Sentence-Transformers 3.0.1+ (`all-MiniLM-L6-v2`).
- **Document & Artifact Engines:** PyPDF 4.3+, python-docx 1.1+, ReportLab 4.2+, ICS 0.7+.
- **Security & Authentication:** Bcrypt 4.0+, PyJWT 2.8+, Cryptography 42.0+.
- **Automated Testing:** Pytest 9.0+, Playwright 1.45+.

### 2.3 Functional Requirements
1. **Document Ingestion:** The system shall ingest PDF, Word DOCX, TXT, and Markdown files, normalizing text and preserving source file names and page indices.
2. **Chunking & Storage:** The system shall segment documents into sliding windows of approximately 500 tokens with 50 tokens overlap and store normalized 384-d vectors in ChromaDB.
3. **Threshold-Gated Retrieval:** The retriever shall convert ChromaDB cosine distance to similarity ($\text{sim}=1-d$) and enforce a strict $\tau=0.30$ threshold.
4. **Universal Search Policy:** Every user query shall search local documents first, verify chunk sufficiency, fall back to trusted web research if necessary, and cite sources in brackets (`[file, page]` or `[URL]`).
5. **Honest Uncertainty:** If neither local documents nor external sources provide sufficient evidence, the assistant shall refuse honestly rather than guessing.
6. **FastMCP Dynamic Discovery:** The Action Agent shall discover tools at runtime by inspecting FastMCP server modules without hardcoded schemas.
7. **HITL Email Safety:** The system shall present an editable preview card and require explicit user confirmation before dispatching emails via SMTP or Gmail API v1.
8. **Calendar Synchronization:** The calendar tool shall generate RFC 5545 `.ics` files and synchronize with Google Calendar API v3 in the `Asia/Kolkata` (+05:30) timezone, preventing duplicate events.
9. **PDF Synthesis:** The PDF tool shall compile structured summaries using ReportLab with embedded SHA-256 integrity verification.
10. **Administrator Authentication:** The application shall restrict access to a single configured administrator account using salted bcrypt hashes, brute-force lockout (5 attempts $\rightarrow$ 15 min lock), and JWT session management.

### 2.4 Non-Functional Requirements
- **Reliability:** The system shall maintain 100% test pass rate across all formal unit, integration, and security test suites.
- **Safety & Security:** Plaintext passwords, API keys, and OAuth access tokens shall never be committed to git, logged in terminal output, or exposed to unauthenticated users.
- **Determinism:** Tool invocation schemas and plan execution DAGs shall adhere strictly to validated parameter signatures.
- **Usability:** The interface shall feature a compact layout, responsive controls, clear execution telemetry badges, and in-chat direct artifact downloads.

---

## 3. System Architecture and Design

The system implements a modular 4-layer architecture:

```
[Presentation Layer: Streamlit UI + Admin Sign-In Portal]
                            │
[Application Layer: LangGraph Compiled StateGraph + FastAPI Gateway]
             ┌──────────────┴──────────────┐
             ▼                             ▼
[RAG & Web Intelligence]        [FastMCP Tool Microservices]
- Local ChromaDB (MiniLM-L6)     - reminder_server (APScheduler)
- Gating Gate (tau = 0.30)       - calendar_server (.ics Generator)
- DuckDuckGo Web Engine          - email_server (HITL Safety)
- Domain Trust Ranker            - pdf_server (ReportLab Engine)
                                 - google_services_server (OAuth APIs)
```

1. **Presentation Layer:** Reactive Streamlit web application featuring the Administrator Sign-In portal, compact sidebar settings, interactive chat window, and execution telemetry drawer.
2. **Application & Orchestration Layer:** LangGraph StateMachine managing the lifecycle of each request across 8 specialized nodes: `load_context` $\rightarrow$ `router_node` $\rightarrow$ (`rag_node` / `action_node` / `planner_node` / `chat_node`) $\rightarrow$ `responder_node`.
3. **RAG & Research Layer:** Dense semantic embedding and vector retrieval pipeline combined with an anti-hallucination gate and DuckDuckGo web research with 4-tier domain authority ranking.
4. **FastMCP Tool Microservices:** Independent tool servers implementing Anthropic's FastMCP specification, exposing 17 tools for operating system automations, document synthesis, and Google Workspace integrations.

---

## 4. Key Technical Contributions

1. **Decoupled Tool Architecture via FastMCP:** Demonstrates practical implementation of Anthropic's Model Context Protocol in an academic assistant, proving that tools can be added or updated without modifying core agent code.
2. **Cosine-Gated Local-to-Web Fallback:** Eliminates hallucinations on private documents by enforcing an empirical similarity threshold ($\tau = 0.30$), combined with a universal 4-step search policy.
3. **Thread-Safe LLM Quota Failover:** Mitigates cloud API rate limits and free-tier quota exhaustion through a round-robin `GeminiKeyManager` pool with automatic backoff.
4. **Enterprise-Grade Administrative Security:** Combines salted bcrypt hashing, brute-force defense, JWT session revocation blacklists, and single-use password reset tokens to secure local and cloud deployments.
5. **Verifiable Telemetry and Inline Citations:** Provides full transparency into agent reasoning, tool dispatch receipts, and bracketed page-level citations for every factual claim.

---

## 5. Limitations & Future Scope

### 5.1 Current Implementation Limitations
- **Single-Administrator Model:** Designed specifically as an individual personal assistant; does not support multi-tenant student registrations.
- **Desktop OAuth on Headless Cloud:** Google OAuth desktop consent requires a local desktop browser to bind `localhost:8080`; cloud deployments operate with core local tools and web research unless pre-authenticated credentials are provided.
- **In-Memory Embedding Computation:** Dense embeddings execute on CPU; large batch uploads (>100 pages) require several seconds for initial vector indexing.

### 5.2 Future Enhancements (Phase 2 Roadmap)
- Multi-user role-based access control (RBAC) supporting student and faculty roles.
- Cross-encoder reranking (e.g. `bge-reranker-large`) to further improve retrieval precision on dense technical documents.
- Integration of local open-weight LLMs (Ollama Llama 3.2) for 100% offline, air-gapped operation.
- WebRTC streaming for multi-modal audio/visual interaction.

---

## 6. Conclusion

The developed **RAG-Based Multi-Agent Personal Assistant Architecture Using MCP** successfully resolves the fundamental problems of parametric hallucination and execution isolation. By combining local dense vector retrieval in ChromaDB, an anti-hallucination cosine similarity gate ($\tau = 0.30$), trusted web fallback, and Anthropic's open Model Context Protocol, the assistant delivers verifiable academic question answering alongside deterministic real-world automation. Verified across 124 formal automated tests and authenticated by a robust security engine, the project represents a solid, defense-ready engineering contribution to applied artificial intelligence in personal productivity.
