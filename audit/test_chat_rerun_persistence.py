import os
import sys
import time
import functools
from pathlib import Path
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print = functools.partial(print, flush=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    page.goto("http://127.0.0.1:8501", wait_until="networkidle")
    time.sleep(2)

    # Generate PDF
    chat_input = page.locator("[data-testid='stChatInput'] textarea")
    chat_input.fill("Create a PDF about upcoming public holidays until November.")
    chat_input.press("Enter")
    
    # Wait for first response
    time.sleep(12)
    dl_buttons_1 = page.locator("button:has-text('Download PDF'), button:has-text('Download')").count()
    print(f"Download buttons after 1st query: {dl_buttons_1}")

    # Send second message (triggering Streamlit internal rerun)
    chat_input = page.locator("[data-testid='stChatInput'] textarea")
    chat_input.fill("Hello, how are you?")
    chat_input.press("Enter")
    time.sleep(8)

    messages = page.locator("[data-testid='stChatMessage']").count()
    dl_buttons_2 = page.locator("button:has-text('Download PDF'), button:has-text('Download')").count()
    print(f"Messages after 2nd query: {messages}")
    print(f"Download buttons after 2nd query (session history persistence): {dl_buttons_2}")
    
    assert dl_buttons_2 >= 1, "Download button did not persist in chat history across reruns!"
    print("SUCCESS: PDF download card persisted in conversation history across rerun!")
    browser.close()
