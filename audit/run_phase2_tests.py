import sys
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = Path("D:/rag-mcp-assistant/audit/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

PHASE2_QUERIES = [
    {
        "id": "2A_doc_qa",
        "query": "Who are the student team members who submitted the Guardian AI project report?",
        "expected_behavior": "Answers from uploaded PDF with verified citations [Guardian_AI_Project_Phase_1_Report 2.0.pdf, page ...]",
        "screenshot": "02_doc_qa_team_members.png"
    },
    {
        "id": "2B_general_web_fallback",
        "query": "What is the capital of Australia and what is its estimated population?",
        "expected_behavior": "Checks local docs first (0 relevant chunks), falls back to trusted web search, cites Canberra and population from reputable source.",
        "screenshot": "03_general_web_fallback.png"
    },
    {
        "id": "2C_ktu_question",
        "query": "What are the minimum SGPA and credit requirements for B.Tech under KTU 2019 scheme regulations?",
        "expected_behavior": "Checks local docs first, searches trusted KTU academic sources (ktu.edu.in), cites authoritative regulations.",
        "screenshot": "04_ktu_scheme_query.png"
    },
    {
        "id": "2D_obscure_refusal",
        "query": "What was the exact secret serial number of the mystical clock in the lost city of Atlantis?",
        "expected_behavior": "Admits honest uncertainty without inventing facts or hallucinating URLs.",
        "screenshot": "05_obscure_refusal.png"
    }
]

def run_phase2():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        # Separate page per test or fresh session to isolate contexts
        for q in PHASE2_QUERIES:
            print(f"\n=======================================================")
            print(f"Running Test {q['id']}: '{q['query']}'")
            print(f"=======================================================")

            context = browser.new_context(viewport={"width": 1366, "height": 950})
            page = context.new_page()

            page.goto("http://localhost:8501", wait_until="networkidle", timeout=30000)
            time.sleep(2)

            chat_input = page.locator("[data-testid='stChatInput'] textarea")
            chat_input.fill(q["query"])
            chat_input.press("Enter")
            print("Prompt submitted, waiting for generation...")

            # Wait for spinner to appear and detach
            try:
                page.wait_for_selector("[data-testid='stSpinner']", state="visible", timeout=10000)
            except Exception:
                pass
            
            page.wait_for_selector("[data-testid='stSpinner']", state="detached", timeout=90000)
            time.sleep(2)

            # Find all expanders (Grounded Sources, Telemetry) and click them so they are expanded in screenshot
            expanders = page.locator("[data-testid='stExpander'] summary").all()
            for exp in expanders:
                try:
                    exp.click()
                    time.sleep(0.5)
                except Exception:
                    pass

            time.sleep(1)

            # Get latest assistant message
            messages = page.locator("[data-testid='stChatMessage']").all()
            latest_text = messages[-1].inner_text() if messages else "NO_RESPONSE"

            shot_path = str(SCREENSHOTS_DIR / q["screenshot"])
            page.screenshot(path=shot_path, full_page=True)
            print(f"Screenshot saved: {shot_path}")

            results.append({
                "id": q["id"],
                "query": q["query"],
                "expected": q["expected_behavior"],
                "response": latest_text,
                "screenshot": shot_path
            })
            context.close()

        browser.close()

    # Save summary json
    with open("D:/rag-mcp-assistant/audit/phase2_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("\nPhase 2 completed and saved to audit/phase2_results.json")

if __name__ == "__main__":
    run_phase2()
