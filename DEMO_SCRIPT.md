# 🎓 KTU S7 B.Tech Project Viva Voce & Demonstration Script

**Project Title:** A Retrieval-Augmented Generation Based Multi-Agent Personal Assistant Architecture Using the Model Context Protocol (MCP)  
**Target Duration:** 15 – 20 Minutes (Demonstration + Viva Questions)

---

## 📋 Pre-Demo Checklist (Prepare 10 Minutes Before Presentation)

1. **Open Terminal 1 (FastAPI Backend Gateway):**
   ```powershell
   Set-Location "D:\rag-mcp-assistant"
   python app/main.py
   ```
   *Verify output: `Uvicorn running on http://0.0.0.0:8000`*

2. **Open Terminal 2 (Streamlit User Interface):**
   ```powershell
   Set-Location "D:\rag-mcp-assistant"
   streamlit run ui/streamlit_app.py
   ```
   *Browser will automatically open at `http://localhost:8501`.*

3. **Browser Tabs to Keep Ready:**
   - **Tab 1:** `http://localhost:8501` (Main Assistant Chat Portal)
   - **Tab 2:** `http://localhost:8501/Evaluation` (Evaluation & Metrics Dashboard)
   - **Tab 3:** `http://localhost:8000/docs` (FastAPI Swagger Interactive Documentation)

---

## 🎬 Step-by-Step Demonstration Script

---

### Scenario 1: Grounded Academic QA with Inline Bracketed Citations

* **Student Prompt to type in Chat:**
  > `"What is Belady's Anomaly and what reference string demonstrates it in FIFO page replacement?"`

* **Expected Assistant Output:**
  > `"Belady's Anomaly is a counter-intuitive phenomenon where increasing the number of allocated physical frames paradoxically increases the total number of page faults under FIFO replacement. The reference string that demonstrates this is: 1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5. With 3 frames it yields 9 page faults, whereas with 4 frames it yields 10 page faults [OS_Unit3_Virtual_Memory_Notes.txt, page 1]."`

* **Examiner Talking Points (What you say):**
  > *"Respected examiners, notice that the assistant does not just give a generic answer. It cites the exact private university document and page number `[OS_Unit3_Virtual_Memory_Notes.txt, page 1]`.*  
  > *If you click the 'Debug & Execution Trace' accordion below the message, you can see our local embedding model (`all-MiniLM-L6-v2`) computed a cosine similarity of ~0.34, passing our anti-hallucination threshold gate ($\tau = 0.30$)."*

---

### Scenario 2: Anti-Hallucination Refusal Gate ($\tau = 0.30$)

* **Student Prompt to type in Chat:**
  > `"Who won the 2022 FIFA World Cup in Qatar?"`

* **Expected Assistant Output:**
  > `"I couldn't find this in your documents."`

* **Examiner Talking Points (What you say):**
  > *"This query tests our anti-hallucination threshold gate. Standard RAG systems force the nearest chunks into the prompt and hallucinate facts or leak training data. In our architecture, the maximum cosine similarity was 0.12, which falls strictly below our $\tau = 0.30$ threshold.*  
  > *The retriever tripped the gate, and the generator immediately returned a pre-emptive refusal without consuming remote LLM tokens. This mathematically guarantees zero hallucinations on out-of-scope queries."*

---

### Scenario 3: FastMCP Tool Execution — Native Desktop Reminder

* **Student Prompt to type in Chat:**
  > `"Remind me to submit the CS432 DBMS Lab mini-project report on 20 March 2026 at 5 PM"`

* **Expected Assistant Output:**
  > Assistant confirms the reminder creation with Reminder ID, scheduled datetime, and note. A native Windows desktop toast notification pops up in the bottom-right corner of your screen!

* **Examiner Talking Points (What you say):**
  > *"Here, the Orchestrator classified the intent as `ACTION` and routed it to our `reminder_server` microservice implemented via the Model Context Protocol (FastMCP).*  
  > *The reminder is persisted in our local SQLite database and scheduled using APScheduler and Plyer, producing an operating system native alert."*

---

### Scenario 4: FastMCP Tool Execution — Calendar Event (.ics Export)

* **Student Prompt to type in Chat:**
  > `"Add the S7 Final Year Project Phase-1 Review on 25 March 2026 from 9:30 AM to 12:00 PM to my calendar"`

* **Expected Assistant Output:**
  > Assistant confirms event creation and provides a link to download the standard RFC 5545 `.ics` file generated in `outputs/events/`.

* **Examiner Talking Points (What you say):**
  > *"Our `calendar_server` microservice created an industry-standard iCalendar file (.ics). Students can import this file directly into Google Calendar, Microsoft Outlook, or Apple Calendar with one click."*

---

### Scenario 5: Human-in-the-Loop (HITL) Security — Email Dispatch

* **Student Prompt to type in Chat:**
  > `"Draft an email to hod.cse@gec.ac.in with subject Project Phase 1 Submission asking for approval"`

* **Expected Assistant Output:**
  > The assistant displays an interactive **Human-in-the-Loop Confirmation Card** in the chat UI with:
  > - Recipient: `hod.cse@gec.ac.in`
  > - Subject: `Project Phase 1 Submission`
  > - Body Preview
  > - **[✅ Confirm & Send]** and **[❌ Cancel]** buttons.

* **Examiner Talking Points (What you say):**
  > *"For security and privacy, actions with real-world side effects (like sending emails) cannot be executed autonomously by the LLM without human oversight. The system creates a pending state and requires explicit Human-in-the-Loop user authorization before firing the SMTP protocol."*

---

### Scenario 6: Multi-Agent Chained Workflow (RAG Retrieval + PDF Compilation)

* **Student Prompt to type in Chat:**
  > `"Summarize the key concepts of Module 3 Virtual Memory from my notes and generate a revision PDF document"`

* **Expected Assistant Output:**
  > 1. LangGraph Orchestrator identifies this as a `CHAINED` intent.
  > 2. Planner decomposes it into two sub-tasks: (1) Retrieve notes via RAG Agent, (2) Synthesize structured PDF via Action Agent.
  > 3. RAG Agent retrieves the lecture notes.
  > 4. Action Agent dispatches to `pdf_server` using ReportLab.
  > 5. Assistant displays the summary in chat alongside a download button for the compiled `.pdf` file located in `outputs/`!

* **Examiner Talking Points (What you say):**
  > *"This demonstrates the power of our LangGraph StateGraph state machine. The system autonomously coordinates multiple specialized agents—retrieving private context first, and then feeding that context into an MCP microservice to produce an academic PDF revision sheet."*

---

### Scenario 7: Interactive Benchmark & Evaluation Dashboard Walkthrough

1. Click on **"1_Evaluation"** in the Streamlit left sidebar navigation (or go to `http://localhost:8501/Evaluation`).
2. Show the examiners:
   - **KPI Metric Cards:**
     - Overall QA Accuracy: **92.5%** (vs Baseline 5.0%)
     - Hallucination Rate: **7.5%** (vs Baseline 95.0% — an 87.5% reduction!)
     - Citation Compliance: **100%**
     - MCP Tool Dispatch Accuracy: **100% (10/10)**
   - **Figure 5.1 & 5.2 Charts:** Show the Matplotlib bar charts comparing Baseline vs RAG.
   - **Q&A Benchmark Explorer:** Show item-by-item comparison where Baseline invented private exam dates while RAG cited exact document pages.

---

## 🎯 High-Probability Viva Defense Questions & Winning Answers

### Q1: What makes the Model Context Protocol (MCP) superior to standard function calling?
> **Answer:** *"Standard function calling embeds function JSON schemas directly into a single model's prompt context, tightly coupling tools to that specific vendor. In contrast, MCP standardizes tool discovery and execution as a decoupled client-server protocol. Any LLM client (Claude, Gemini, Ollama) can discover our MCP servers over standard pipes without changing the tool implementation."*

### Q2: Why did you pick `sentence-transformers/all-MiniLM-L6-v2` instead of an API embedding?
> **Answer:** *"Three reasons: First, **Data Privacy**—private university notes and timetables never leave the student's machine. Second, **Zero Quota Exhaustion**—bulk indexing of large PDFs will never fail due to API rate limits. Third, **Speed**—local inference takes less than 20 milliseconds per query."*

### Q3: What is the significance of the $\tau = 0.30$ threshold gate?
> **Answer:** *"Without the threshold gate, vector databases return the nearest K chunks even if they have 0% relevance to the query. For example, asking about the FIFA World Cup would return the closest Operating Systems chunk, tempting the LLM to hallucinate or leak out-of-domain knowledge. The threshold gate ensures that if semantic similarity is below 0.30, the pipeline refuses immediately without wasting LLM tokens."*
