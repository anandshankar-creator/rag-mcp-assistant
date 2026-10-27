import sys
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = Path("D:/rag-mcp-assistant/audit/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

def run_query(query: str, screenshot_name: str):
    print(f"\n=======================================================")
    print(f"Running UI Query: '{query}'")
    print(f"=======================================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 950})

        page.goto("http://127.0.0.1:8501", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        chat_input = page.locator("[data-testid='stChatInput'] textarea")
        chat_input.fill(query)
        chat_input.press("Enter")
        print("Prompt submitted, waiting for response...")

        # Wait for spinner to appear and detach
        try:
            page.wait_for_selector("[data-testid='stSpinner']", state="visible", timeout=8000)
            print("Spinner active...")
        except Exception:
            pass

        page.wait_for_selector("[data-testid='stSpinner']", state="detached", timeout=120000)
        print("Spinner finished, rendering output...")
        time.sleep(2)

        # Expand all expanders (Sources, Debug trace)
        expanders = page.locator("[data-testid='stExpander'] summary").all()
        for exp in expanders:
            try:
                exp.click()
                time.sleep(0.3)
            except Exception:
                pass
        time.sleep(1)

        # Get response text
        messages = page.locator("[data-testid='stChatMessage']").all()
        resp_text = messages[-1].inner_text() if messages else "NO_MESSAGE"

        shot_path = str(SCREENSHOTS_DIR / screenshot_name)
        page.screenshot(path=shot_path, full_page=True)
        print(f"Screenshot saved to: {shot_path}")

        print("--- Response Snippet ---")
        try:
            print(resp_text[:500])
        except Exception:
            print(resp_text.encode("ascii", "replace").decode()[:500])

        page.close()
        browser.close()
        return resp_text

if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "What are the minimum SGPA and credit requirements for B.Tech under KTU 2019 scheme regulations?"
    s = sys.argv[2] if len(sys.argv) > 2 else "04_ktu_scheme_query.png"
    run_query(q, s)
