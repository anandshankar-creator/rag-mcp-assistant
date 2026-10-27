import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = Path("D:/rag-mcp-assistant/audit/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

def test_chat_interaction(prompt_text: str, screenshot_name: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()

        print(f"Navigating to http://localhost:8501 ...")
        page.goto("http://localhost:8501", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # Type message in chat input
        chat_input = page.locator("[data-testid='stChatInput'] textarea")
        chat_input.fill(prompt_text)
        chat_input.press("Enter")
        print(f"Submitted prompt: {prompt_text}")

        # Wait for Streamlit to start and then finish processing
        try:
            page.wait_for_selector("[data-testid='stSpinner']", state="visible", timeout=10000)
            print("Spinner appeared, waiting for it to finish...")
        except Exception:
            pass
        
        page.wait_for_selector("[data-testid='stSpinner']", state="detached", timeout=60000)
        print("Spinner detached, response rendered!")
        time.sleep(2)

        # Get all chat messages
        messages = page.locator("[data-testid='stChatMessage']").all()
        print(f"Total chat messages on screen: {len(messages)}")
        
        last_msg = messages[-1].inner_text() if messages else "NO MESSAGE"
        print("--- Latest Assistant Response ---")
        try:
            print(last_msg[:400])
        except UnicodeEncodeError:
            print(last_msg[:400].encode('ascii', 'replace').decode())

        shot_path = str(SCREENSHOTS_DIR / screenshot_name)
        page.screenshot(path=shot_path, full_page=True)
        print(f"Screenshot saved to: {shot_path}")

        browser.close()
        return last_msg

if __name__ == "__main__":
    test_chat_interaction(
        "Who are the student team members who submitted the Guardian AI project report?",
        "02_doc_qa_team_members.png"
    )
