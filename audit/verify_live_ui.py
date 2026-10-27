import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = Path("D:/rag-mcp-assistant/audit/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

def inspect_phase_1():
    console_logs = []
    network_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("requestfailed", lambda req: network_errors.append(f"FAILED: {req.url} ({req.failure})"))

        print("Navigating to http://localhost:8501 ...")
        page.goto("http://localhost:8501", wait_until="networkidle", timeout=30000)
        time.sleep(3)

        title = page.title()
        print(f"Page Title: {title}")

        # Check Sidebar
        sidebar = page.locator("[data-testid='stSidebar']")
        sidebar_visible = sidebar.is_visible()
        sidebar_text = sidebar.inner_text() if sidebar_visible else "NOT VISIBLE"

        # Check Stored Documents
        docs_header_visible = page.locator("text=Stored Documents").is_visible()
        
        # Check File Uploader
        uploader_visible = page.locator("[data-testid='stFileUploader']").is_visible()

        # Check Chat Input
        chat_input = page.locator("[data-testid='stChatInput'] textarea")
        chat_input_visible = chat_input.is_visible()

        # Save Phase 1 Screenshot
        shot1 = str(SCREENSHOTS_DIR / "01_initial_ui_load.png")
        page.screenshot(path=shot1, full_page=True)

        res = {
            "title": title,
            "sidebar_visible": sidebar_visible,
            "sidebar_text": sidebar_text,
            "docs_header_visible": docs_header_visible,
            "uploader_visible": uploader_visible,
            "chat_input_visible": chat_input_visible,
            "screenshot": shot1,
            "console_logs_count": len(console_logs),
            "console_logs": console_logs[:10],
            "network_errors_count": len(network_errors),
            "network_errors": network_errors,
        }

        print("\n--- Phase 1 Verification Results ---")
        print(json.dumps({k: v for k, v in res.items() if k != "sidebar_text"}, indent=2))
        print("\n--- Sidebar Text Preview ---")
        print(sidebar_text[:600])

        browser.close()
        return res

if __name__ == "__main__":
    inspect_phase_1()
