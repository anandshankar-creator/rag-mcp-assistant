# Production Smoke Test Plan: Live Streamlit Deployment

**Project**: RAG-Based Multi-Agent Personal Assistant Using MCP  
**Live URL**: `https://rag-mcp-assistant-mf654govkzfnjjmmtlgxfqw.streamlit.app`  
**Target Administrator**: `sergio759516@gmail.com`  
**Execution Environment**: Streamlit Community Cloud  
**Audit Date**: October 2026  

---

## 1. Scope & Objective

This verification checklist outlines the exact step-by-step procedure to validate the live public Streamlit Cloud deployment after code updates and secrets synchronization. It covers end-to-end security, administrative authentication, profile persistence, document Q&A, web fallback, MCP tool execution, and session lifecycle management.

---

## 2. Test Execution Checklist

### Phase 1: Authentication & Security Verification

#### Test 1.1: Canonical Administrator Login Pre-fill
- **Action**: Navigate to `https://rag-mcp-assistant-mf654govkzfnjjmmtlgxfqw.streamlit.app`.
- **Expected Result**:
  - The page displays the Administrator Sign-In portal with 🔒 icon.
  - The `Administrator Email` input is pre-filled with `sergio759516@gmail.com`.
  - Placeholder text reflects `sergio759516@gmail.com`.
  - No legacy `admin@assistant.local` text appears anywhere on the screen.

#### Test 1.2: Incorrect Password & Generic Error
- **Action**: Enter an incorrect password (e.g. `WrongPass999!`) and click **Sign In**.
- **Expected Result**:
  - An error banner appears: `❌ Invalid email or password.`
  - The system does not reveal whether the email exists.
  - The user remains unauthenticated on the login page.

#### Test 1.3: Successful Administrator Login
- **Action**: Enter the configured administrator password and click **Sign In**.
- **Expected Result**:
  - Success toast appears: `Signed in successfully!`
  - The application navigates to the main assistant interface.
  - The sidebar header displays: `👤 Admin: sergio759516@gmail.com`.

#### Test 1.4: Password Recovery ("Forgot Password?")
- **Action**: Click **Forgot Password?** from the login page.
- **Expected Result**:
  - Displays the Password Recovery page with 🔑 icon.
  - The email field is pre-filled with `sergio759516@gmail.com`.
  - Clicking **Send Reset Link**:
    - If mail secrets are configured: Success notification confirming dispatch.
    - If mail secrets are unconfigured: Clear diagnostic notice and emergency expander displaying the single-use recovery link.
  - Pasting the recovery link opens the Set New Password view with single-use SHA-256 token validation.

---

### Phase 2: Administrator Profile & Sidebar Layout

#### Test 2.1: Admin Settings Compact UI
- **Action**: Inspect the sidebar under the status indicator.
- **Expected Result**:
  - Section header reads: `⚙️ Admin Settings`.
  - Field label and placeholder read: `Admin Name`.
  - There is **no** University Email input field.
  - The layout is compact and consistent with Admin design rules.

#### Test 2.2: Profile Update Persistence
- **Action**: Edit Admin Name to `Sergio Admin` and click **Save Profile**.
- **Expected Result**:
  - Toast notification appears: `Admin profile updated!`.
  - Reloading the browser page preserves `Sergio Admin`.

---

### Phase 3: Document-First RAG & Trusted Web Fallback

#### Test 3.1: Document-First Question Answering
- **Action**: In the chat box, ask a question answered by the indexed syllabus (e.g., *"What are the course objectives of KTU CS301 Theory of Computation?"*).
- **Expected Result**:
  - The assistant retrieves local document chunks from ChromaDB.
  - The answer cites the exact source document and page number (e.g. `[Source: CS301_TOC.pdf, Page 1]`).
  - Retrieval route is logged as `retrieval_route: document_first`.

#### Test 3.2: Trusted Web Fallback on General Queries
- **Action**: Ask a general question not present in the uploaded documents (e.g., *"What is the latest 2026 KTU B.Tech academic calendar notification?"*).
- **Expected Result**:
  - Local retrieval score falls below `RAG_SIMILARITY_THRESHOLD (0.30)`.
  - Trusted web search fallback executes automatically.
  - Results prioritize authoritative `.ac.in`, `.edu`, and official KTU domains with trust scores $\ge 0.45$.

---

### Phase 4: Model Context Protocol (MCP) Tool Execution

#### Test 4.1: Task Reminder Tool
- **Action**: Type: *"Set a reminder to submit the final report draft tomorrow at 4 PM"*.
- **Expected Result**:
  - Action Agent invokes `create_reminder` from `reminder_server`.
  - Returns a structured execution receipt with reminder ID and formatted timestamp in `Asia/Kolkata` timezone.

#### Test 4.2: Human-in-the-Loop (HITL) Email Safety Gate
- **Action**: Type: *"Send an email to supervisor@university.edu with subject Project Update"*.
- **Expected Result**:
  - The assistant creates a draft preview using `preview_email`.
  - The assistant halts execution and prompts: *"User confirmation is required before dispatching external emails."*
  - No email is sent until explicit confirmation is provided.

#### Test 4.3: Styled PDF Generation & Chat Download Button
- **Action**: Type: *"Generate a PDF summary of my current project milestones"*.
- **Expected Result**:
  - Action Agent executes `generate_pdf` from `pdf_server`.
  - A formatted ReportLab PDF is generated.
  - A native Streamlit download button (`📥 Download PDF (milestones_summary.pdf)`) appears directly in the chat message.
  - Clicking the button downloads the valid PDF file to the client browser.

---

### Phase 5: Session Termination & Logout

#### Test 5.1: Administrator Logout
- **Action**: Click the **🚪 Logout** button in the sidebar.
- **Expected Result**:
  - The JWT access token is revoked and blacklisted in SQLite `revoked_tokens`.
  - All session state variables (`auth_token`, `authenticated`, `messages`) are cleared.
  - The user is redirected to the Administrator Sign-In screen.
  - Attempting to access protected URLs directly redirects to the login screen.
