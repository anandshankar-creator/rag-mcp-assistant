# UI Screenshot Capture Guide & Visual Evidence Catalog

**Audit Standard:** Strict Verification of Real Playwright Screenshot Captures in `D:\rag-mcp-assistant\audit\screenshots\`  
**Image Format:** High-Resolution PNG (1280x800 Viewport)  
**Total Verified Screenshots on Disk:** 11  
**Re-capture Script:** `python audit/verify_live_ui.py` and `python audit/verify_auth_flow.py`

---

## 1. Master Screenshot Inventory Table

| Figure / Screenshot Number | Screenshot File Path | Screen / UI State | Architectural Purpose in Report | Reproduction Steps | Expected Visual Evidence |
|---|---|---|---|---|---|
| **Fig 6.1 (Screen 01)** | [`audit/screenshots/01_initial_ui_load.png`](file:///D:/rag-mcp-assistant/audit/screenshots/01_initial_ui_load.png) | Main Dashboard Initial Load | Proves clean UI rendering, custom CSS typography, active knowledge base, and model badge | Navigate to `http://localhost:8501` as authenticated user | Clean dual-pane interface; compact sidebar with profile and knowledge base list; empty chat prompt |
| **Fig 6.2 (Screen 02)** | [`audit/screenshots/02_doc_qa_team_members.png`](file:///D:/rag-mcp-assistant/audit/screenshots/02_doc_qa_team_members.png) | Document-First QA with Inline Citations | Demonstrates local RAG retrieval and bracketed page citation grounding | Ask: *"Summarize the uploaded project report"* | Grounded response citing `[Guardian_AI_Project_Phase_1_Report 2.0.pdf, page X]` with `Route: QA` badge |
| **Fig 6.3 (Screen 03)** | [`audit/screenshots/03_general_web_fallback.png`](file:///D:/rag-mcp-assistant/audit/screenshots/03_general_web_fallback.png) | Trusted Web Fallback with External Links | Demonstrates automatic local-to-web fallback when document evidence is insufficient | Ask: *"When is the next public holiday in Kerala?"* | Response with live authoritative URLs and `Route: QA` / `Source: web_fallback` telemetry |
| **Fig 6.4 (Screen 04)** | [`audit/screenshots/04_ktu_scheme_query.png`](file:///D:/rag-mcp-assistant/audit/screenshots/04_ktu_scheme_query.png) | Domain Trust Ranking on KTU Queries | Demonstrates Tier 1 domain authority filtering on university regulations | Ask: *"What are the KTU 2019 scheme B.Tech project rules?"* | Grounded response prioritizing `ktu.edu.in` circulars |
| **Fig 6.5 (Screen 05)** | [`audit/screenshots/05_obscure_refusal.png`](file:///D:/rag-mcp-assistant/audit/screenshots/05_obscure_refusal.png) | Anti-Hallucination Refusal Gate | Demonstrates honest uncertainty when neither local docs nor web sources verify the answer | Ask an obscure unverified query | Exact honest refusal message: *"I couldn't verify this information from your documents..."* |
| **Fig 6.6 (Screen 06)** | [`audit/screenshots/06_compact_sidebar.png`](file:///D:/rag-mcp-assistant/audit/screenshots/06_compact_sidebar.png) | Compact Student Settings Section | Shows compact sidebar layout without unnecessary email fields | Inspect left sidebar under Student Settings | Compact layout consistent with Admin Settings; student name field; university email removed |
| **Fig 6.7 (Screen 07)** | [`audit/screenshots/07_chat_pdf_delivery.png`](file:///D:/rag-mcp-assistant/audit/screenshots/07_chat_pdf_delivery.png) | PDF Generation & Direct In-Chat Download | Demonstrates FastMCP ReportLab synthesis and authenticated download delivery | Ask: *"Generate a PDF report on Operating Systems Virtual Memory"* | Execution receipt card with green status and inline `Download PDF` button inside chat |
| **Fig 6.8 (Screen 08)** | [`audit/screenshots/08_login_screen.png`](file:///D:/rag-mcp-assistant/audit/screenshots/08_login_screen.png) | Administrator Sign-In Portal | Proves complete unauthenticated access blocking via `st.stop()` | Open browser in incognito mode at `http://localhost:8501` | Professional login card; sidebar, chat, and uploaded documents are completely hidden |
| **Fig 6.9 (Screen 09)** | [`audit/screenshots/09_forgot_password_screen.png`](file:///D:/rag-mcp-assistant/audit/screenshots/09_forgot_password_screen.png) | Administrator Password Recovery View | Demonstrates secure forgot-password workflow and rate limiting | Click "Forgot Password?" link on login screen | Clean recovery interface requesting admin email; anti-enumeration generic confirmation |
| **Fig 6.10 (Screen 10)**| [`audit/screenshots/10_reset_password_screen.png`](file:///D:/rag-mcp-assistant/audit/screenshots/10_reset_password_screen.png) | Single-Use Password Reset Form | Demonstrates single-use token consumption and password policy enforcement | Navigate to `http://localhost:8501/?action=reset_password&token=<valid_token>` | Password reset form with New Password and Confirm Password inputs |
| **Fig 6.11 (Screen 11)**| [`audit/screenshots/11_authenticated_dashboard.png`](file:///D:/rag-mcp-assistant/audit/screenshots/11_authenticated_dashboard.png) | Authenticated Administrator Dashboard | Demonstrates active authenticated session with security badge and logout control | Log in with valid administrator credentials | Dashboard showing `🛡️ Administrator` badge, compact settings, active chat, and Logout button |

---

## 2. Instructions for Manual Re-Capture

If higher-resolution or alternative operating system captures are desired for the final report printout:
1. Ensure both the FastAPI backend and Streamlit frontend are running:
   ```powershell
   # Terminal 1:
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   # Terminal 2:
   python -m streamlit run ui/streamlit_app.py --server.port 8501
   ```
2. Open Google Chrome or Microsoft Edge at `http://localhost:8501`.
3. Set your browser zoom level to 100% and window resolution to $1920 \times 1080$.
4. Use the Windows Snipping Tool (`Win + Shift + S`) to capture the respective screen state as described in the table above.
5. Save captured images into `audit/screenshots/` replacing or supplementing existing captures.
