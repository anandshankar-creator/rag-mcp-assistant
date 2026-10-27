# Academic Chapter Mapping: Sample Report to Actual Project

**Target Project:** A Retrieval-Augmented Generation Based Multi-Agent Personal Assistant Architecture Using the Model Context Protocol (MCP)  
**Sample Reference Authority:** Guardian AI Phase 1 Report (LMCST / KTU Standard)

---

## 1. Structural Section-by-Section Mapping

| Sample Report Section (Guardian AI) | Corresponding Section in RAG-MCP Assistant Report | Technical Focus in Actual Codebase |
|---|---|---|
| **Cover & Title Page** | Cover & Title Page | KTU B.Tech CSE Project Title: *RAG-Based Multi-Agent Personal Assistant Architecture Using the Model Context Protocol (MCP)* |
| **Declaration & Certificate** | Declaration & Certificate | Institutional faculty signatures (Guide, Coordinator, HoD) and bonafide student declaration |
| **Acknowledgement (Page i)** | Acknowledgement (Page i) | Gratitude to Guide, HoD, Department faculty, and peers |
| **Abstract (Page ii)** | Abstract (Page ii) | 3-paragraph summary: (1) LLM hallucinations & tool silos, (2) RAG + $\tau=0.30$ gating + DuckDuckGo trust ranker + FastMCP microservices + LangGraph, (3) 124 formal tests, zero credential leaks, Streamlit UI |
| **Table of Contents** | Table of Contents | Complete pagination and heading hierarchy |
| **List of Tables (Page iii)** | List of Tables (Page iii) | Table 3.1 Hardware Specs, Table 3.2 Software Stack, Table 4.1 Module Inventory, Table 6.1 Hosting Constraints & Cloud Adaptations |
| **List of Figures (Page iv)** | List of Figures (Page iv) | Fig 5.1 System Architecture, Fig 5.2 RAG Ingestion Pipeline, Fig 5.3 LangGraph State Machine, Fig 5.4 MCP Client-Server Dispatch |
| **Chapter 1: INTRODUCTION** | **Chapter 1: INTRODUCTION** | Problem context: LLMs as closed silos unable to query local private files or execute operating system tools safely |
| *1.1 Objectives* | *1.1 Objectives* | 10 concrete engineering goals (local RAG, $\tau=0.30$ gating, FastMCP decoupling, HITL safety, dual Gemini pool rotation, admin auth) |
| **Chapter 2: LITERATURE REVIEW** | **Chapter 2: LITERATURE REVIEW** | Review of 4 existing paradigms: (1) Closed-book LLMs (ChatGPT/Claude), (2) Standard Naive RAG, (3) LangChain monolithic tool wrappers, (4) Commercial assistants (Google Assistant/Siri) |
| *2.1 Existing Solutions* | *2.1 Existing Solutions* | Detailed examination of current conversational agents and naive RAG pipelines |
| *2.2 Limitations of Current Solutions* | *2.2 Limitations of Current Solutions* | 6 critical gaps: Parametric hallucination on private data, lack of evidence thresholds, tool-vendor coupling, API quota vulnerability, absence of admin security gates, zero verified read-back |
| *2.3 Proposed Solutions* | *2.3 Proposed Solutions* | Proposed Multi-Agent RAG + FastMCP architecture resolving each limitation |
| **Chapter 3: SYSTEM ANALYSIS** | **Chapter 3: SYSTEM ANALYSIS** | Formal requirements engineering |
| *3.1 System Requirements* | *3.1 System Requirements* | Table 3.1 Hardware (CPU/RAM/Disk for embeddings & ChromaDB), Table 3.2 Software (Python 3.11, Streamlit, LangGraph, FastMCP, SQLite) |
| *3.2 User Requirements* | *3.2 User Requirements* | 10 user requirements: Local doc QA, verified citations, calendar scheduling, email previews, report generation, admin login |
| *3.3 Functional Requirements* | *3.3 Functional Requirements* | 18 functional requirements: Ingestion, chunking, similarity calculation, threshold refusal, web fallback, MCP discovery, HITL confirmation, JWT auth |
| *3.4 Non-Functional Requirements* | *3.4 Non-Functional Requirements* | Ranked: Reliability (100% test pass), Privacy/Security (zero plaintext secrets, bcrypt hashing), Determinism, Execution Latency, Usability |
| **Chapter 4: MODULES** | **Chapter 4: MODULES** | 12 discrete architectural modules: Ingestion, Embeddings, Gated Retrieval, Web Research, Orchestrator, Planner, Action Agent, FastMCP Tools, LLM Key Manager, Admin Auth, SQLite Memory, Streamlit UI |
| **Chapter 5: SYSTEM ARCHITECTURE & DATA FLOW** | **Chapter 5: SYSTEM ARCHITECTURE & DATA FLOW** | Formal diagrams and execution state machines |
| *5.1 System Architecture Overview* | *5.1 Architecture Overview* | 4-layer design: Presentation (Streamlit), API/Orchestration (FastAPI/LangGraph), Intelligence (RAG & Web Fallback), Tool Microservices (FastMCP) |
| *5.2 Architecture Diagram* | *5.2 Architecture Diagram* | Fig 5.1 Overall Multi-Agent System Architecture |
| *5.3 Data Flow Diagram* | *5.3 Ingestion & RAG Data Flow* | Fig 5.2 Document Ingestion, Chunking, ChromaDB storage & Retrieval Flow |
| *5.4 Emergency State Machine* | *5.4 LangGraph State Machine* | Fig 5.3 LangGraph State Machine: load_context -> router -> (rag/action/chat/planner) -> responder |
| **Chapter 6: IMPLEMENTATION** | **Chapter 6: IMPLEMENTATION** | Detailed software engineering implementation |
| *6.1 Frontend Development* | *6.1 Frontend Development* | Streamlit reactive interface, custom CSS typography, HITL confirmation cards, telemetry drawer, compact Student Settings |
| *6.2 Security and Access Control* | *6.2 Security & Authentication* | Administrator-only authentication: salted bcrypt (`rounds=12`), brute-force lockout, JWT tokens with SQLite revocation blacklist, single-use SHA-256 reset tokens |
| *6.3 Backend and Data Layer* | *6.3 Backend & Persistence* | 10 SQLite tables (`assistant.db`), persistent ChromaDB vector collection (`student_knowledge_base`), FastAPI gateway |
| *6.4 Emergency Detection & Communication* | *6.4 RAG Gating, Web Search & MCP* | Cosine similarity formula ($\text{sim}=1-d$), $\tau=0.30$ anti-hallucination gate, DuckDuckGo web fallback, 17 FastMCP tools across 5 microservices |
| *6.5 Android Restrictions & Alternatives* | *6.5 Cloud Hosting Constraints & Adaptations* | Table 6.1 Matrix: In-process execution vs daemon uvicorn, `pysqlite3-binary` patch for Linux ChromaDB, Desktop OAuth vs Cloud credentials |
| **Chapter 7: CONCLUSION** | **Chapter 7: CONCLUSION** | Summary of implemented system, 124 passing tests, verified defense capabilities, and future Phase 2 roadmap |
| **APPENDIX** | **APPENDIX** | 25 oral defense presentation slides (Slide 1 Title to Slide 25 References) |
| **REFERENCES** | **REFERENCES** | IEEE references: Anthropic MCP, LangGraph, Lewis et al. (RAG), Reimers et al. (Sentence-BERT), ChromaDB, Gemini API |

---

## 2. Key Terminology Alignment

To guarantee that the final report maintains rigorous alignment with the approved sample:
- The section naming convention `Chapter 01`, `Chapter 02`, etc., will match the sample.
- The 4-layer architectural breakdown in Chapter 5 directly mirrors the sample's Clean Architecture approach.
- The 12-module decomposition in Chapter 4 provides identical depth and structure to the sample report.
- Table 6.1 ("Hosting Constraints and Legitimate Alternatives") adopts the exact comparative analysis format used in the sample's "Android Restrictions and Legitimate Alternatives" table.
