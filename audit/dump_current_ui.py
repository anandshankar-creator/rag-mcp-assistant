import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page()
    page.goto("http://localhost:8501", timeout=30000)
    time.sleep(3)

    msgs = page.locator("[data-testid='stChatMessage']").all()
    print(f"Total msgs on current page: {len(msgs)}")
    for i, m in enumerate(msgs):
        txt = m.inner_text().replace('\n', ' ')
        try:
            print(f"Msg {i}: {txt[:200]}")
        except Exception:
            print(f"Msg {i}: {txt.encode('ascii', 'replace').decode()[:200]}")
    
    spinner = page.locator("[data-testid='stSpinner']")
    print(f"Spinner visible: {spinner.is_visible()}")

    page.screenshot(path="D:/rag-mcp-assistant/audit/screenshots/current_state.png", full_page=True)
    b.close()
