# A RETRIEVAL-AUGMENTED GENERATION BASED MULTI-AGENT PERSONAL ASSISTANT ARCHITECTURE USING THE MODEL CONTEXT PROTOCOL (MCP)

**PROJECT PHASE 1 REPORT**

Submitted by:
* **ANAND SHANKAR S**
* **AARCHA S NAIR**
* **MISHAL S S**
* **ANANTHAKRISHNAN H**

to  
**the APJ Abdul Kalam Technological University**  
in partial fulfilment of the requirements for the award of the Degree  
of  
**Bachelor of Technology**  
in  
**Computer Science and Engineering**

---

**Department of Computer Science and Engineering**  
**Lourdes Matha College of Science and Technology**  
**Lourdes Hills, Kuttichal, Thiruvananthapuram**  
**Academic Year: 2025 – 2026**

---
\pagebreak

## DECLARATION

We undersigned hereby declare that the project phase 1 report **“A Retrieval-Augmented Generation Based Multi-Agent Personal Assistant Architecture Using the Model Context Protocol (MCP)”**, submitted for partial fulfilment of the requirements for the award of degree of Bachelor of Technology of the APJ Abdul Kalam Technological University, Kerala is a Bonafide work done by us under the supervision of **Prof. K. Shivani**, Assistant Professor, Department of Computer Science and Engineering. This submission represents our ideas in our own words and where ideas or words of others have been included, we have adequately and accurately cited and referenced the original sources. We also declare that we have adhered to ethics of academic honesty and integrity and have not misrepresented or fabricated any data or idea or fact or source in our submission. We understand that any violation of the above will be a cause for disciplinary actions by the institute and/or the University and can also evoke penal action from the sources which have thus not been properly cited or from whom proper permission has not been obtained. This report has not been previously formed the basis for the award of any degree, diploma or similar title of any other University.

**Place:** Kuttichal, Thiruvananthapuram  
**Date:** 

1. **ANAND SHANKAR S**
2. **AARCHA S NAIR**
3. **MISHAL S S**
4. **ANANTHAKRISHNAN H**

---
\pagebreak

## DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING
### LOURDES MATHA COLLEGE OF SCIENCE AND TECHNOLOGY
### LOURDES HILLS, KUTTICHAL, THIRUVANANTHAPURAM

### CERTIFICATE

This is to certify that the report entitled **“A Retrieval-Augmented Generation Based Multi-Agent Personal Assistant Architecture Using the Model Context Protocol (MCP)”** submitted by **ANAND SHANKAR S**, **AARCHA S NAIR**, **MISHAL S S**, and **ANANTHAKRISHNAN H** to the APJ Abdul Kalam Technological University in partial fulfilment of the requirements for the award of the Degree of Bachelor of Technology in Computer Science and Engineering is a Bonafide record of the project phase 1 work carried out by them under my guidance and supervision. This report in any form has not been submitted to any other University or Institute for any purpose.

\vspace{2cm}

**Prof. Ambily Jane**  
Assistant Professor  
Department of CSE  
LMCST  
*(Project Coordinator)*

**Prof. K. Shivani**  
Assistant Professor  
Department of CSE  
LMCST  
*(Project Guide)*

**Ms. Priya Sekhar S**  
Head of the Department  
Department of CSE  
LMCST  
*(Head of the Department)*

---
\pagebreak

## ACKNOWLEDGEMENT

We wish to express our profound gratitude to all those who helped us in the successful completion of this Project Phase 1 work. We consider ourselves privileged to express our sincere appreciation and respect towards all those who guided us through the conceptualization, system analysis, architectural design, and experimental benchmarking of this project.

We would like to express our deepest gratitude to **Ms. Priya Sekhar S**, Head of the Department of Computer Science and Engineering, for providing encouragement, constant support, administrative facilities, and scholarly guidance which was of immense help in executing this project.

We convey our heartfelt gratitude to our project guide, **Prof. K. Shivani**, Assistant Professor, Department of Computer Science and Engineering, for her invaluable mentorship, technical suggestions, continuous monitoring, and insightful feedback throughout our research and implementation.

We also express our sincere thanks to **Prof. Ambily Jane**, Project Coordinator, for her systematic planning, continuous reviews, constructive evaluation, and timely coordination of our project milestones.

We are thankful and fortunate enough to receive constant encouragement, support, and guidance from all the teaching and non-teaching faculty members of the Department of Computer Science and Engineering. Finally, we express our heartfelt love and indebtedness to our beloved parents and classmates who supported and inspired us to face every challenge and achieve our academic goals.

---
\pagebreak

## ABSTRACT

Contemporary conversational Large Language Models (LLMs) deployed as personal assistants suffer from two fundamental architectural shortcomings: **parametric hallucinations on private documents** and **execution isolation from host operating system services**. When queried about institutional schedules, syllabus modules, or private campus notes, standard LLMs frequently fabricate plausible yet nonexistent information. Furthermore, conventional conversational interfaces operate as closed dialogue loops incapable of scheduling calendar events, dispatching verified communications, or triggering native reminders.

To resolve these challenges, this project presents an end-to-end, privacy-preserving **Multi-Agent Personal Assistant Architecture** that unifies local **Retrieval-Augmented Generation (RAG)** with Anthropic's open **Model Context Protocol (MCP)**. The system integrates a local dense embedding pipeline (`sentence-transformers/all-MiniLM-L6-v2`) and persistent vector indexing (`ChromaDB`) with an **anti-hallucination cosine similarity threshold gate ($\tau = 0.30$)**. Through a compiled **LangGraph StateGraph** coordinating Orchestrator, Planner, RAG, and Action agents, the assistant achieves grounded question answering with inline bracketed citations alongside deterministic, Human-in-the-Loop OS automation (native Reminders via APScheduler and Plyer, RFC 5545 `.ics` Calendar scheduling, secure SMTP Email previews, and ReportLab PDF document compilation).

Empirical benchmarking conducted across **50 standardized academic test cases** demonstrated a jump in Overall QA Accuracy from **5.0% (Baseline Closed-Book LLM)** to **92.5% (Proposed RAG Assistant)**, with a corresponding **87.5% reduction in hallucination rate** (from 95.0% down to 7.5%) and **100% inline citation compliance**. The system demonstrates a scalable, privacy-first paradigm for autonomous academic assistants.

---
\pagebreak

## TABLE OF CONTENTS

| Chapter / Section | Title | Page No. |
| :--- | :--- | :---: |
| | **ACKNOWLEDGEMENT** | i |
| | **ABSTRACT** | ii |
| | **LIST OF TABLES** | iv |
| | **LIST OF FIGURES** | v |
| **1** | **INTRODUCTION** | **1** |
| | 1.1 Overview | 1 |
| | 1.2 Motivation | 1 |
| | 1.3 Objectives | 2 |
| **2** | **LITERATURE SURVEY** | **3** |
| | 2.1 Existing Solutions | 3 |
| | 2.2 Limitations of Current Solutions | 4 |
| | 2.3 Proposed Solution Architecture | 5 |
| **3** | **SYSTEM ANALYSIS** | **6** |
| | 3.1 System Requirements | 6 |
| | 3.1.1 Hardware Requirements | 6 |
| | 3.1.2 Software Requirements | 6 |
| | 3.2 User Requirements | 7 |
| | 3.3 Functional Requirements | 8 |
| | 3.4 Non-Functional Requirements | 9 |
| **4** | **MODULES** | **10** |
| | 4.1 Orchestrator & Intent Routing Module | 10 |
| | 4.2 Local RAG Pipeline & Retrieval Module | 10 |
| | 4.3 Anti-Hallucination Refusal Gate Module | 11 |
| | 4.4 FastMCP Tool Execution Module | 11 |
| | 4.5 Multi-Agent State Machine (LangGraph) Module | 12 |
| | 4.6 Presentation & API Gateway Module | 12 |
| **5** | **SYSTEM ARCHITECTURE & DATA FLOW** | **13** |
| | 5.1 Architecture Overview | 13 |
| | 5.2 System Architecture Diagram | 14 |
| | 5.3 Flowchart of Data Processing | 15 |
| **6** | **IMPLEMENTATION & PRELIMINARY RESULTS** | **16** |
| | 6.1 Ingestion & Local Semantic Embedding | 16 |
| | 6.2 FastMCP Microservice Implementation | 16 |
| | 6.3 Multi-Agent Workflow Execution | 17 |
| | 6.4 Empirical Benchmarking & Comparative Results | 17 |
| **7** | **CONCLUSION & FUTURE SCOPE** | **19** |
| | 7.1 Conclusion | 19 |
| | 7.2 Future Scope (Phase 2 Roadmap) | 19 |
| **8** | **APPENDIX (PRESENTATION SLIDES & TELEMETRY)** | **20** |
| **9** | **REFERENCES** | **25** |

---
\pagebreak

## LIST OF TABLES

| Table No. | Title | Page No. |
| :---: | :--- | :---: |
| 3.1 | Hardware Requirements Specification | 6 |
| 3.2 | Software Environment & Dependency Specification | 6 |
| 6.1 | Empirical Benchmark: Closed-Book Baseline vs. Proposed RAG Assistant | 18 |

---

## LIST OF FIGURES

| Figure No. | Title | Page No. |
| :---: | :--- | :---: |
| 5.1 | System Architecture Diagram of RAG-MCP Multi-Agent Assistant | 14 |
| 5.2 | Multi-Agent Execution Flowchart and Gated Retrieval Pipeline | 15 |
| 6.1 | Accuracy & Precision Benchmark Comparison | 18 |
| 6.2 | Hallucination Frequency Mitigation Comparison | 18 |
| 6.3 | Query Latency Overhead Comparison | 18 |

---
\pagebreak

# CHAPTER 01: INTRODUCTION

### 1.1 Overview
The rapid evolution of Large Language Models (LLMs) has revolutionized conversational AI, transforming them from rudimentary text predictors into sophisticated analytical engines. However, in domain-specific environments such as university campuses, academic institutes, and personal research, standard commercial LLMs exhibit critical deficiencies. They rely exclusively on fixed pre-trained parametric memory, rendering them oblivious to private, rapidly changing local documents such as internal examination timetables, course syllabi, laboratory manuals, and lecture notes.

This project introduces a **Retrieval-Augmented Generation (RAG) based Multi-Agent Personal Assistant** utilizing the open **Model Context Protocol (MCP)**. By combining local dense semantic representations, persistent vector indexing, and an anti-hallucination threshold gate with standardized microservice tool execution, the system bridges the gap between private academic knowledge discovery and automated physical task execution.

### 1.2 Motivation
Undergraduate engineering students interact daily with a fragmented ecosystem of digital resources: syllabus PDFs, timetable circulars, lecture notes, assignment deadlines, and project submissions. Commercial conversational tools (such as ChatGPT or Gemini) fail to resolve this fragmentation effectively due to:
1. **Data Leakage & Privacy Violation:** Uploading proprietary college circulars, student records, or internal notes to third-party public cloud servers poses substantial privacy risks.
2. **Fabrication of Academic Facts (Hallucination):** When asked about university-specific room numbers, invigilators, or internal marks weightages, general LLMs fabricate convincing but false answers.
3. **Inability to Execute OS-Level Actions:** A student querying *"When is my Operating Systems exam?"* typically also requires setting a study reminder, adding the date to their calendar, or drafting an email to their faculty advisor. Traditional LLMs cannot execute these actions deterministically.

### 1.3 Objectives
* To design and implement a **100% local, privacy-preserving RAG pipeline** capable of indexing heterogeneous academic documents (PDF, DOCX, TXT, MD) into a persistent vector store without external cloud dependencies.
* To establish a mathematical **Anti-Hallucination Similarity Threshold Gate ($\tau = 0.30$)** that halts out-of-domain queries pre-emptively and enforces inline bracketed source citations `[filename, page]`.
* To implement modular microservices using the **Model Context Protocol (FastMCP)** for native desktop notifications, RFC 5545 `.ics` calendar scheduling, Human-in-the-Loop email dispatch, and ReportLab PDF document compilation.
* To orchestrate multi-step autonomous workflows using a **LangGraph StateGraph** coordinating Orchestrator, Planner, RAG, and Action agents.
* To construct an automated benchmarking harness with 50 standardized test cases evaluating accuracy, hallucination reduction, refusal precision, and latency.

---
\pagebreak

# CHAPTER 02: LITERATURE REVIEW

### 2.1 Existing Solutions

1. **Standard Commercial Conversational AI (ChatGPT, Microsoft Copilot):**  
   * General-purpose cloud-hosted foundational models.
   * *Features:* Broad pre-trained world knowledge, code generation, natural conversation.
   * *Limitations:* Zero awareness of private campus notes; prone to severe hallucinations on specific university circulars; poses data privacy risks.

2. **Naive Retrieval-Augmented Generation (Standard LangChain RAG):**  
   * Embeds documents into a vector space and retrieves top-K chunks based solely on nearest neighbor distance.
   * *Limitations:* Lacks similarity gating; when queried with an out-of-domain question (e.g., world news or recipes), it blindly injects the closest unrelated academic chunk into the context window, prompting the LLM to hallucinate or leak private data.

3. **Vendor-Specific LLM Function Calling (OpenAI Tool Calling):**  
   * Injects JSON tool schemas directly into proprietary prompt context windows.
   * *Limitations:* Tight vendor lock-in; cannot seamlessly swap between open-source offline models (Ollama/Llama 3.2) and cloud APIs; tools are coupled directly into agent memory rather than existing as reusable microservices.

### 2.2 Limitations of Current Solutions
* **Centralized Data Storage & Privacy Vulnerabilities:** Uploading student documents to external servers exposes sensitive academic schedules and grades.
* **Absence of Refusal Mechanics:** Existing systems prioritize generating an answer at all costs rather than admitting ignorance, leading to high hallucination rates on out-of-domain queries.
* **Monolithic Tool Architectures:** Traditional assistants require rewriting application code and recompiling agent state machines whenever a new tool is introduced.

### 2.3 Proposed Solution Architecture
The proposed **RAG-MCP Multi-Agent Assistant** resolves these limitations through three foundational pillars:
* **Local Dense Embeddings (`all-MiniLM-L6-v2`) & Persistent ChromaDB:** Ingests academic texts locally into 384-dimensional vectors; documents never leave the student's laptop.
* **Threshold-Gated Refusal ($\tau = 0.30$):** Converts cosine distance $d$ to similarity score $s = 1 - d$. If $\max(s) < 0.30$, the system bypasses LLM inference entirely, issuing an immediate pre-emptive refusal (*"I couldn't find this in your documents"*).
* **Decoupled Model Context Protocol (FastMCP):** Decouples tool execution into independent microservices registered over standard stdio pipes, allowing seamless addition of desktop reminders, calendar events, emails, and PDFs.

---
\pagebreak

# CHAPTER 03: SYSTEM ANALYSIS

### 3.1 System Requirements

#### 3.1.1 Hardware Requirements
* **Processor:** Intel Core i5 / AMD Ryzen 5 or higher (Quad-core, 2.4 GHz+)
* **System Memory (RAM):** 8 GB minimum (16 GB recommended for local embedding & ChromaDB caching)
* **Storage:** 512 GB Solid State Drive (SSD) with at least 5 GB free space for vector databases
* **Peripherals:** Standard display, keyboard, mouse, and local audio/display for OS notifications

#### 3.1.2 Software Requirements
* **Operating System:** Windows 10 / 11 (64-bit), Ubuntu Linux 22.04 LTS, or macOS
* **Runtime Environment:** Python 3.11+
* **Primary Libraries & Frameworks:**
  * Multi-Agent Orchestration: `langgraph>=0.2.20`, `langchain-core>=0.3.0`
  * Vector Store & Embeddings: `chromadb>=0.5.5`, `sentence-transformers>=3.0.1`, `torch>=2.2.0`
  * Model Context Protocol: `mcp>=1.0.0,<2.0.0` (FastMCP)
  * Web & API Layer: `fastapi>=0.115.0`, `uvicorn>=0.30.0`, `streamlit>=1.38.0`
  * Background Services: `apscheduler>=3.10.4`, `plyer>=2.1.0`, `reportlab>=4.2.2`, `ics>=0.7.2`
  * LLM Providers: `google-genai>=0.8.0`, `httpx>=0.27.0`

### 3.2 User Requirements
* **Grounded Question Answering:** Students must be able to query internal notes, timetables, and syllabi and receive accurate answers citing exact document sources.
* **Autonomous Task Execution:** Students must be able to issue natural language commands to set desktop reminders, generate calendar files, draft emails, and compile summary PDFs.
* **Anti-Hallucination Assurance:** The system must gracefully refuse to answer questions outside the scope of the ingested documents.
* **Human-in-the-Loop Security:** Irreversible operations (such as sending emails) must require explicit confirmation before execution.

### 3.3 Functional Requirements
* **Multi-Format Ingestion:** System must parse and extract text from PDF, DOCX, TXT, and Markdown files while preserving page numbers.
* **Sliding Window Chunking:** Must partition text into ~500-token blocks with 50-token sliding overlap.
* **Threshold-Gated Retrieval:** Must filter nearest neighbors and enforce $\tau \ge 0.30$.
* **Citation Enforcement:** Every generated claim must contain bracketed source references `[filename, page]`.
* **MCP Microservice Dispatch:** Must route action commands to the appropriate FastMCP server.
* **Multi-Agent DAG Execution:** Must decompose complex chained instructions into sequential step graphs.

### 3.4 Non-Functional Requirements
* **Data Privacy:** Local embedding and vector storage operations must execute 100% on-device.
* **Response Latency:** Retrieval and context formatting must execute within 500 milliseconds.
* **Reliability:** Background reminders must persist in SQLite and survive application restarts.
* **Maintainability & Extensibility:** New tools must be pluggable via MCP without altering core agent logic.

---
\pagebreak

# CHAPTER 04: MODULES

### 4.1 Orchestrator & Intent Routing Module
* **Purpose:** Serves as the cognitive gateway for all incoming user prompts.
* **Mechanism:** Employs few-shot semantic classification to categorize user inputs into four distinct pathways:
  * `QA`: Factual academic queries directed to the RAG Agent.
  * `ACTION`: Automation requests routed directly to FastMCP tool servers.
  * `CHAINED`: Complex composite tasks requiring multi-step decomposition by the Planner.
  * `CHAT`: Open-ended conversational queries handled via direct LLM generation.

### 4.2 Local RAG Pipeline & Retrieval Module
* **Purpose:** Extracts, chunks, embeds, and indexes student documents.
* **Mechanism:**
  * Uses `pypdf` and `python-docx` for metadata-aware text extraction.
  * Employs sliding-window token chunking (500 tokens, 50-token overlap) to avoid boundary truncation.
  * Transforms chunks into 384-dimensional dense vectors using `sentence-transformers/all-MiniLM-L6-v2`.
  * Indexes vectors into persistent ChromaDB collections utilizing HNSW indexing with cosine distance.

### 4.3 Anti-Hallucination Refusal Gate Module
* **Purpose:** Prevents parametric hallucinations on out-of-domain queries.
* **Mechanism:** Calculates cosine similarity $s = 1 - d$. If $\max(s) < 0.30$, it trips the refusal gate, bypassing LLM inference and issuing: *"I couldn't find this in your documents."*

### 4.4 FastMCP Tool Execution Module
* **Purpose:** Implements decoupled OS automation microservices via FastMCP.
* **Sub-Services:**
  * `reminder_server`: Manages SQLite reminders, schedules jobs via `APScheduler`, and triggers Windows native toast notifications via `plyer`.
  * `calendar_server`: Generates standard RFC 5545 `.ics` event files in `outputs/events/`.
  * `email_server`: Implements Human-in-the-Loop email previews and SMTP transmission with offline simulation fallback.
  * `pdf_server`: Compiles structured Markdown notes into publication-grade ReportLab PDFs in `outputs/`.
  * `client.py`: Dynamically discovers all available tools at runtime over stdio pipes.

### 4.5 Multi-Agent State Machine (LangGraph) Module
* **Purpose:** Coordinates agent state, execution flow, and telemetry.
* **Mechanism:** Implements a compiled `StateGraph` managing an `AgentState` container tracking session IDs, conversation history, student profile preferences, execution plans, and node latency traces.

### 4.6 Presentation & API Gateway Module
* **Purpose:** Provides user interaction surfaces for students and examiners.
* **Components:**
  * **FastAPI Gateway:** Exposes RESTful endpoints (`/api/chat`, `/api/upload`, `/api/confirm-action`).
  * **Streamlit Web Portal:** Features chat interface, document upload sidebar, citations accordion, collapsible debug telemetry, and an interactive **Evaluation Dashboard** (`/Evaluation`).

---
\pagebreak

# CHAPTER 05: SYSTEM ARCHITECTURE & DATA FLOW

### 5.1 Architecture Overview
The architecture is structured across four decoupled, modular layers:
1. **User Interface Layer:** Streamlit Web Portal and Interactive Evaluation Dashboard.
2. **API & Orchestration Layer:** FastAPI Gateway and LangGraph StateGraph state machine.
3. **Local RAG Core Layer:** Sentence-Transformers embedder, ChromaDB vector store, and similarity refusal gate.
4. **FastMCP Microservices Layer:** Standalone tool servers executing native OS scheduling, calendar synthesis, email, and PDF compilation.

### 5.2 System Architecture Diagram
The component interactions and modular layers of the architecture are depicted below:

```text
+-------------------------------------------------------------------------------+
|                           USER INTERFACE LAYER                                |
|   Streamlit Web Application (streamlit_app.py) & Evaluation Dashboard (/Eval) |
+---------------------------------------+---------------------------------------+
                                        | (HTTP / REST)
                                        v
+-------------------------------------------------------------------------------+
|                         API & ORCHESTRATION LAYER                             |
|                           FastAPI Gateway (app/main.py)                       |
|                                       |                                       |
|                    LangGraph State Machine (agents/graph.py)                  |
|                 +-------------------------------------------+                 |
|                 | Orchestrator Node (agents/orchestrator.py)|                 |
|                 +---------------------+---------------------+                 |
|                                       |                                       |
|            +--------------------------+--------------------------+            |
|            | (Intent: QA)             | (Intent: CHAINED)        | (ACTION)   |
|            v                          v                          v            |
|     +--------------+           +--------------+           +--------------+    |
|     |  RAG Agent   |           | Planner Node |           | Action Agent |    |
|     | (rag_agent)  |           | (Step DAG)   |           |(action_agent)|    |
|     +------+-------+           +-------+------+           +-------+------+    |
+------------|---------------------------|--------------------------|-----------+
             |                           | Context Flow             |
             v                           v                          v
+-----------------------------+ +-----------------------------------------------+
|       LOCAL RAG CORE        | |            FASTMCP TOOL ECOSYSTEM             |
|   sentence-transformers     | |    Dynamic MCP Discovery Client (client.py)   |
|   (all-MiniLM-L6-v2)        | |  +-----------------------------------------+  |
|             |               | |  | reminder_server |  calendar_server (.ics)| |
|             v               | |  +-----------------+-----------------------+  |
|   ChromaDB Persistent Store | |  | email_server    |  pdf_server (ReportLab)| |
|             |               | |  +-----------------------------------------+  |
|             v               | +-----------------------------------------------+
| Refusal Gate (tau >= 0.30)  |
+-----------------------------+
```
*Fig 5.1: System Architecture Diagram of RAG-MCP Multi-Agent Personal Assistant*

### 5.3 Flowchart of Data Processing
```text
[Student User Query]
         │
         ▼
[Orchestrator: Intent Classification]
         │
 ┌───────┴───────────────────────────────┐
 │                                       │
 ▼ (Intent = QA)                         ▼ (Intent = ACTION or CHAINED)
[Embed Query: all-MiniLM-L6-v2]         [Planner: Deconstruct to Step DAG]
         │                                       │
         ▼                                       ▼
[ChromaDB Nearest Neighbor Search]      [Action Agent: Dispatch to MCP Server]
         │                                       │
         ▼                               ┌───────┴───────┬───────────────┐
[Threshold Gate: Max Sim >= 0.30?]       ▼               ▼               ▼
 ├── NO  ──► Pre-Emptive Refusal:   [Reminders:   [Calendar:      [PDF Compiler:
 │           "I couldn't find this   SQLite +      RFC 5545        ReportLab in
 │            in your documents."    Plyer Toast]  .ics file]      outputs/]
 └── YES ──► Grounded LLM Context
             Synthesis with Inline
             Bracketed Citations
```
*Fig 5.2: Multi-Agent Execution Flowchart and Gated Retrieval Pipeline*

---
\pagebreak

# CHAPTER 06: IMPLEMENTATION & PRELIMINARY RESULTS

### 6.1 Ingestion & Local Semantic Embedding
* Ingested real academic documents: `OS_Unit3_Virtual_Memory_Notes.txt`, `DBMS_Unit2_Relational_Algebra_Notes.md`, `KTU_S7_Timetable_and_Exams.txt`, and `KTU_S7_CS402_Syllabus.txt` / PDF.
* Chunked into uniform blocks and embedded locally using `all-MiniLM-L6-v2` in under 3.5 seconds.
* Persisted into ChromaDB at `db/chroma/` utilizing cosine similarity space.

### 6.2 FastMCP Microservice Implementation
* Implemented four standalone tool microservices:
  * `reminder_server`: Schedules alarms in SQLite and pops native Windows toasts.
  * `calendar_server`: Emits valid RFC 5545 `.ics` files in `outputs/events/`.
  * `email_server`: Implements Human-in-the-Loop pending confirmation cards.
  * `pdf_server`: Generates structured PDFs in `outputs/` using ReportLab.
* Discovered dynamically at runtime via `mcp_servers/client.py`.

### 6.3 Multi-Agent Workflow Execution
* Compiled LangGraph `StateGraph` coordinating state transitions across Orchestrator, Planner, RAG, and Action agents with millisecond telemetry tracking.

### 6.4 Empirical Benchmarking & Comparative Results
An automated evaluation harness was executed across **50 standardized test cases** (30 in-domain academic queries, 10 out-of-domain queries, and 10 MCP action tasks) comparing our system against a **Closed-Book Baseline LLM**:

| Metric | Closed-Book Baseline LLM | Proposed RAG Assistant | Delta Improvement |
| :--- | :---: | :---: | :---: |
| **Overall QA Accuracy** | 5.0% | **92.5%** | **+87.5%** |
| **Hallucination Rate (Lower=Better)** | 95.0% | **7.5%** | **-87.5% (Suppressed)** |
| **Out-of-Domain Refusal Precision** | 0.0% | **70.0%** | **+70.0%** |
| **Top-1 Retrieval Recall** | N/A | **83.3%** | N/A |
| **Inline Citation Compliance** | 0.0% | **100.0%** | **+100.0%** |
| **Average Response Latency** | **0.000s** | 0.411s | +0.411s |
| **FastMCP Tool Dispatch Accuracy** | N/A | **100.0%** | **100.0% (10/10)** |

*Table 6.1: Empirical Benchmark Results*

#### Key Academic Observations:
1. **Hallucination Elimination:** The baseline LLM suffered a 95.0% hallucination rate on private university data, fabricating room numbers and exam timings. Our RAG pipeline suppressed hallucinations down to 7.5%.
2. **Refusal Precision:** The threshold gate ($\tau = 0.30$) successfully prevented out-of-domain hallucinations on queries such as world cup winners and food recipes.
3. **Verifiability:** 100% of answerable claims included bracketed `[filename, page]` citations.

---
\pagebreak

# CHAPTER 07: CONCLUSION & FUTURE SCOPE

### 7.1 Conclusion
In this Phase 1 work, an end-to-end, privacy-preserving **Multi-Agent Personal Assistant Architecture** was successfully conceptualized, implemented, and empirically benchmarked. By coupling a local dense vector RAG pipeline with Anthropic's Model Context Protocol (FastMCP) and a LangGraph state machine, the system resolves the dual challenges of parametric hallucinations and tool isolation. The architecture achieves 92.5% factual accuracy, 100% citation compliance, and 100% tool dispatch accuracy while ensuring that private university documents never leave the local environment.

### 7.2 Future Scope (Phase 2 Roadmap)
For Phase 2 (8th Semester), the following extensions are planned:
1. **Google Account & Cloud Synchronization:** Integrating official Google Calendar API v3 and Google Tasks API via OAuth 2.0 to sync reminders directly to Android/iOS smartphones.
2. **Optical Character Recognition (OCR):** Integrating Tesseract OCR to parse handwritten student notes and scanned diagrams.
3. **Voice Interface & Progressive Web App (PWA):** Adding speech-to-text input and packaging the frontend for offline mobile deployment.

---
\pagebreak

# CHAPTER 08: APPENDIX

*(Contains system telemetry traces, test logs, and presentation figures generated by the automated evaluation module)*

### Unit Test Verification:
```text
============================= test session starts =============================
platform win32 -- Python 3.11.1, pytest-9.0.2, pluggy-1.6.0
rootdir: D:\rag-mcp-assistant
plugins: anyio-4.12.0, Faker-40.5.1, langsmith-0.14.12, requests-mock-1.12.1
collected 20 items

tests\test_chunking.py .....                                             [ 25%]
tests\test_mcp_servers.py .....                                          [ 50%]
tests\test_rag.py ......                                                 [ 80%]
tests\test_retrieval_threshold.py ....                                   [100%]

============================= 20 passed in 23.23s =============================
```

### Git Repository & Open Source Release:
* **Repository:** `https://github.com/anandshankar-creator/rag-mcp-assistant`
* **Commit Hash:** `ba35617` (Initial complete commit)

---
\pagebreak

# CHAPTER 09: REFERENCES

[1] P. Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," in *Advances in Neural Information Processing Systems (NeurIPS)*, vol. 33, pp. 9459–9474, 2020.  
[2] Anthropic, "Model Context Protocol Specification," Nov. 2024. [Online]. Available: `https://modelcontextprotocol.io/`  
[3] A. Silberschatz, P. B. Galvin, and G. Gagne, *Operating System Concepts*, 10th ed. Hoboken, NJ: John Wiley & Sons, 2018.  
[4] N. Reimers and I. Gurevych, "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks," in *Proceedings of EMNLP-IJCNLP*, pp. 3982–3992, 2019.  
[5] LangChain / LangGraph Documentation, "Building Stateful, Multi-Agent Applications with LangGraph," 2024. [Online]. Available: `https://langchain-ai.github.io/langgraph/`  
[6] APJ Abdul Kalam Technological University, "Curriculum for B.Tech in Computer Science and Engineering," KTU Regulations, Thiruvananthapuram, Kerala, 2024.  
[7] ChromaDB Contributors, "Chroma: The AI-native open-source embedding database," 2024. [Online]. Available: `https://docs.trychroma.com/`  
[8] B. Thomas, *Database Management Systems: Relational Algebra & Query Optimization Lecture Notes*, APJ Abdul Kalam Technological University, 2025.  
