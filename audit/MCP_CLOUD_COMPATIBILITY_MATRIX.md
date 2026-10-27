# Model Context Protocol (MCP) Cloud Compatibility Matrix

**Project**: RAG-Based Multi-Agent Personal Assistant Using MCP  
**Architecture**: 5 FastMCP Server Modules, 17 Dynamically Discovered Tools  
**Protocol Standard**: Model Context Protocol (FastMCP) over in-process stdio discovery  
**Target Environment**: Streamlit Community Cloud (Linux container) & Localhost (Windows/macOS)  
**Audit Date**: October 2026  

---

## 1. Architecture Overview

The system adheres to the Model Context Protocol (MCP) standard, enabling dynamic tool discovery (`list_tools()`) and schema normalization. The Action Agent discovers tools at runtime rather than hardcoding them, proving the architectural claim: *"New tools can be plugged into the assistant without modifying the core orchestrator."*

The 17 discovered tools span 5 specialized FastMCP servers:
1. `reminder_server`: Local deadline and task reminder management.
2. `calendar_server`: Local academic schedule and timetable management.
3. `email_server`: Email previewing and multi-provider transmission (Gmail API / SMTP).
4. `pdf_server`: ReportLab document compilation and styled PDF generation.
5. `google_services_server`: Official Google Workspace cloud integrations (Calendar, Gmail, Tasks, Drive, Notes).

---

## 2. Comprehensive Tool Compatibility Matrix

| # | Tool Name | Server Module | Transport | Required Secrets | Filesystem Dependencies | Persistence Mode | Cloud Compatibility Status |
|---|-----------|---------------|-----------|------------------|-------------------------|------------------|----------------------------|
| **1** | `create_reminder` | `reminder_server` | FastMCP / In-Process | None | SQLite at `db/assistant.db` | SQLite (`reminders` table) | **Full Support** *(Ephemeral filesystem on cloud reboots)* |
| **2** | `list_reminders` | `reminder_server` | FastMCP / In-Process | None | SQLite at `db/assistant.db` | SQLite query | **Full Support** |
| **3** | `delete_reminder` | `reminder_server` | FastMCP / In-Process | None | SQLite at `db/assistant.db` | SQLite deletion | **Full Support** |
| **4** | `create_event` | `calendar_server` | FastMCP / In-Process | None | SQLite at `db/assistant.db` | SQLite (`calendar_events` table) | **Full Support** *(Ephemeral filesystem on cloud reboots)* |
| **5** | `list_events` | `calendar_server` | FastMCP / In-Process | None | SQLite at `db/assistant.db` | SQLite query | **Full Support** |
| **6** | `delete_event` | `calendar_server` | FastMCP / In-Process | None | SQLite at `db/assistant.db` | SQLite deletion | **Full Support** |
| **7** | `preview_email` | `email_server` | FastMCP / In-Process | None | Memory / Temp preview | Read-only formatting | **Full Support** (HITL Gate) |
| **8** | `send_email` | `email_server` | FastMCP / In-Process | `GMAIL_USER` + `GMAIL_APP_PASSWORD` or `GOOGLE_TOKEN_JSON` | Optional attachment from `outputs/` | External Provider (Google API / SMTP) + Action Log | **Full Support** *(Requires secrets configured in Streamlit Cloud)* |
| **9** | `generate_pdf` | `pdf_server` | FastMCP / In-Process | None | Writable `outputs/` directory | Filesystem PDF + Session state | **Full Support** *(Rendered directly via Streamlit download button)* |
| **10** | `google_calendar_create_event` | `google_services_server` | FastMCP / In-Process | `GOOGLE_TOKEN_JSON` or `[google_oauth]` | In-memory token parsing | External Google Calendar API v3 | **Conditional** *(Requires OAuth refresh token in Streamlit Secrets)* |
| **11** | `google_calendar_list_events` | `google_services_server` | FastMCP / In-Process | `GOOGLE_TOKEN_JSON` or `[google_oauth]` | In-memory token parsing | External Google Calendar API v3 | **Conditional** *(Requires OAuth refresh token in Streamlit Secrets)* |
| **12** | `google_gmail_send_message` | `google_services_server` | FastMCP / In-Process | `GOOGLE_TOKEN_JSON` or `[google_oauth]` | In-memory token parsing | External Gmail REST API v1 | **Conditional** *(Requires OAuth refresh token in Streamlit Secrets)* |
| **13** | `google_gmail_list_messages` | `google_services_server` | FastMCP / In-Process | `GOOGLE_TOKEN_JSON` or `[google_oauth]` | In-memory token parsing | External Gmail REST API v1 | **Conditional** *(Requires OAuth refresh token in Streamlit Secrets)* |
| **14** | `google_tasks_create` | `google_services_server` | FastMCP / In-Process | `GOOGLE_TOKEN_JSON` or `[google_oauth]` | In-memory token parsing | External Google Tasks API v1 | **Conditional** *(Requires OAuth refresh token in Streamlit Secrets)* |
| **15** | `google_tasks_list` | `google_services_server` | FastMCP / In-Process | `GOOGLE_TOKEN_JSON` or `[google_oauth]` | In-memory token parsing | External Google Tasks API v1 | **Conditional** *(Requires OAuth refresh token in Streamlit Secrets)* |
| **16** | `google_drive_search` | `google_services_server` | FastMCP / In-Process | `GOOGLE_TOKEN_JSON` or `[google_oauth]` | In-memory token parsing | External Google Drive API v3 | **Conditional** *(Requires OAuth refresh token in Streamlit Secrets)* |
| **17** | `google_keep_note` | `google_services_server` | FastMCP / In-Process | None / SQLite fallback | SQLite at `db/assistant.db` | SQLite notes storage | **Full Support** *(With documented API architecture rationale)* |

---

## 3. Server-by-Server Forensic Analysis

### 3.1 `reminder_server` & `calendar_server`
- **Transport**: In-process FastMCP instantiation (`FastMCP("reminder_server")`).
- **Dependencies**: Python standard library (`datetime`, `zoneinfo`, `sqlite3`).
- **Filesystem Assumptions**: Expects `db/assistant.db` to exist or be created by `app.config.Settings.ensure_directories()`.
- **Cloud Considerations**: Streamlit Community Cloud instances provide an ephemeral filesystem. SQLite transactions persist for the duration of the container's lifecycle. During container re-starts or app re-deploys, un-backed SQLite data resets to its initial state.
- **Fail-Soft Safety**: No external network dependencies; 100% operational offline and in air-gapped test runners.

### 3.2 `email_server`
- **Transport**: In-process FastMCP tool dispatching.
- **Dependencies**: `email`, `smtplib`, `mimetypes`, `base64`, `google-api-python-client`.
- **Dual-Mode Dispatching**:
  1. Priority 1 (Official Gmail API): Invoked if Google OAuth credentials exist.
  2. Priority 2 (Standard Gmail SMTP): Invoked via `smtp.gmail.com:587` with STARTTLS if `GMAIL_USER` and `GMAIL_APP_PASSWORD` are present.
- **HITL Safeguard**: Strictly halts unconfirmed operations. Requires explicit `confirmed=True` argument before transmission.
- **Idempotency**: Prevents duplicate sends on retries by querying existing message subjects and recipients.
- **Cloud Considerations**: Fully functional on Streamlit Cloud when configured with an App Password or OAuth secret.

### 3.3 `pdf_server`
- **Transport**: In-process FastMCP tool dispatching.
- **Dependencies**: `reportlab` (canvas, styles, platypus).
- **Filesystem Assumptions**: Writes output files to `outputs/<filename>.pdf`.
- **Cloud Considerations**: Streamlit Cloud instances allow writes to local container subdirectories (`outputs/`). To prevent file loss on browser reloads, `ui/streamlit_app.py` caches the generated PDF bytes in `st.session_state.pdf_registry` and displays a persistent `st.download_button()`.

### 3.4 `google_services_server`
- **Transport**: In-process FastMCP tool dispatching.
- **Dependencies**: `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`.
- **OAuth Manager Architecture**: Uses `mcp_servers.google_auth.GoogleAuthManager`.
- **Cloud Resolution**:
  - Localhost: Reads `credentials/google_token.json`.
  - Streamlit Cloud: Reads `st.secrets["GOOGLE_TOKEN_JSON"]` or `st.secrets["google_oauth"]`.
- **Honest Diagnostics**: If credentials are absent, tools return a structured diagnostic receipt (`status: unconfigured`) explaining exact setup steps rather than crashing or pretending a mock is real.

---

## 4. Verification Evidence

- All 17 tools are dynamically discovered at runtime by `mcp_servers.client.MCPClientController`.
- All 8 unit tests in `tests/test_mcp_servers.py` pass cleanly.
- Automated tests in `tests/test_email_regression.py` and `tests/test_google_calendar_regression.py` verify diagnostic honesty and fail-soft boundaries.
