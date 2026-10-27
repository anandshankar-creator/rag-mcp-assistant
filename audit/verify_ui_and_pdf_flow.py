import os
import sys
import time
import json
import functools
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print = functools.partial(print, flush=True)

SCREENSHOTS_DIR = Path("D:/rag-mcp-assistant/audit/screenshots")
DOWNLOADS_DIR = Path("D:/rag-mcp-assistant/audit/downloads")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

def verify_all():
    results = {}
    console_logs = []
    network_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
        page = context.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("requestfailed", lambda req: network_errors.append(f"FAILED: {req.url} ({req.failure})"))

        print("1. Loading http://127.0.0.1:8501 ...")
        page.goto("http://127.0.0.1:8501", wait_until="networkidle", timeout=30000)
        time.sleep(3)

        # 1. Inspect Sidebar
        sidebar = page.locator("[data-testid='stSidebar']")
        sidebar_text = sidebar.inner_text()
        print(f"Sidebar text length: {len(sidebar_text)}")
        
        has_email = "University Email" in sidebar_text or "email" in sidebar_text.lower().split()
        results["university_email_present"] = "University Email" in sidebar_text
        print(f"Is 'University Email' present: {results['university_email_present']} (Expected: False)")

        # Verify Student Name input exists
        name_input = sidebar.locator("input[type='text']")
        results["student_name_input_exists"] = name_input.count() > 0
        print(f"Student name inputs found: {name_input.count()}")

        # Check Save Profile button
        save_btn = sidebar.locator("button:has-text('Save Profile'), button:has-text('Save')")
        results["save_button_exists"] = save_btn.count() > 0
        print(f"Save button found: {save_btn.count()}")

        # Try changing name and clicking Save
        if name_input.count() > 0 and save_btn.count() > 0:
            name_input.first.fill("Test Student Sergio")
            save_btn.first.click()
            time.sleep(2)
            print("Profile saved successfully.")

        # Check sidebar scroll height vs client height
        scroll_info = page.evaluate("""() => {
            const el = document.querySelector("[data-testid='stSidebarUserContent']");
            if (!el) return { scrollHeight: 0, clientHeight: 0 };
            return { scrollHeight: el.scrollHeight, clientHeight: el.clientHeight };
        }""")
        results["sidebar_scroll_info"] = scroll_info
        print(f"Sidebar heights: scrollHeight={scroll_info['scrollHeight']}, clientHeight={scroll_info['clientHeight']}")

        # Screenshot 06: Compact Sidebar
        shot06 = str(SCREENSHOTS_DIR / "06_compact_sidebar.png")
        page.screenshot(path=shot06, full_page=False)
        results["screenshot_06"] = shot06
        print(f"Saved Screenshot 06: {shot06}")

        # 2. Test PDF Generation via Chat
        chat_prompt = "Create a PDF about upcoming public holidays until November."
        print(f"\n2. Submitting query: '{chat_prompt}' ...")
        
        chat_input = page.locator("[data-testid='stChatInput'] textarea")
        chat_input.fill(chat_prompt)
        chat_input.press("Enter")

        # Wait for assistant response
        print("Waiting for assistant response to render (up to 120s) ...")
        start_time = time.time()
        response_found = False

        while time.time() - start_time < 120:
            messages = page.locator("[data-testid='stChatMessage']")
            if messages.count() >= 2: # At least 1 user message and 1 assistant message
                last_msg = messages.last
                msg_text = last_msg.inner_text()
                # Check if it finished streaming / processing
                if ("Your PDF is ready" in msg_text or "Download PDF" in msg_text or ".pdf" in msg_text) and not page.locator(".stSpinner").is_visible():
                    response_found = True
                    break
                # Also check if an action-card or error appeared
                if "Action Output" in msg_text or "Download PDF" in msg_text:
                    if not page.locator(".stSpinner").is_visible():
                        response_found = True
                        break
            time.sleep(2)

        elapsed = round(time.time() - start_time, 2)
        print(f"Assistant responded in {elapsed}s. Response found: {response_found}")

        assistant_messages = page.locator("[data-testid='stChatMessage']")
        last_assistant_text = assistant_messages.last.inner_text() if assistant_messages.count() > 0 else ""
        print("\n--- Assistant Message Text ---")
        print(last_assistant_text[:800])

        results["assistant_response_text"] = last_assistant_text
        results["pdf_ready_in_text"] = "Your PDF is ready" in last_assistant_text
        results["download_pdf_in_text"] = "Download PDF" in last_assistant_text

        # 3. Locate and click st.download_button
        download_btn = page.locator("button:has-text('Download PDF'), button:has-text('Download')")
        print(f"Download buttons found: {download_btn.count()}")
        results["download_button_count"] = download_btn.count()

        downloaded_file_path = None
        if download_btn.count() > 0:
            print("Clicking download button...")
            with page.expect_download(timeout=15000) as download_info:
                download_btn.last.click()
            download = download_info.value
            downloaded_file_path = DOWNLOADS_DIR / download.suggested_filename
            download.save_as(str(downloaded_file_path))
            print(f"Downloaded file saved to: {downloaded_file_path}")

            # Verify downloaded PDF
            if downloaded_file_path.exists():
                file_size = downloaded_file_path.stat().st_size
                with open(downloaded_file_path, "rb") as f:
                    header = f.read(5)
                results["downloaded_file"] = {
                    "filename": download.suggested_filename,
                    "size_bytes": file_size,
                    "header": str(header),
                    "is_valid_pdf": header == b"%PDF-" and file_size > 0
                }
                print(f"Downloaded PDF Validation: {results['downloaded_file']}")

        # Screenshot 07: Chat PDF Delivery
        shot07 = str(SCREENSHOTS_DIR / "07_chat_pdf_delivery.png")
        page.screenshot(path=shot07, full_page=False)
        results["screenshot_07"] = shot07
        print(f"Saved Screenshot 07: {shot07}")

        # 4. Check rerun persistence
        print("\n4. Testing chat persistence across rerun/refresh...")
        page.reload(wait_until="networkidle")
        time.sleep(3)
        reloaded_messages = page.locator("[data-testid='stChatMessage']")
        print(f"Messages after reload: {reloaded_messages.count()}")
        reloaded_dl_btns = page.locator("button:has-text('Download PDF'), button:has-text('Download')")
        print(f"Download buttons after reload: {reloaded_dl_btns.count()}")
        results["persistence"] = {
            "messages_count": reloaded_messages.count(),
            "download_buttons_count": reloaded_dl_btns.count(),
            "persisted": reloaded_dl_btns.count() > 0
        }

        browser.close()

    # Save results json
    results_path = Path("D:/rag-mcp-assistant/audit/phase6_pdf_ui_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved results to {results_path}")

if __name__ == "__main__":
    verify_all()
