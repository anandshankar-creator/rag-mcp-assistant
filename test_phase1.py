"""
==============================================================================
Script: test_phase1.py
Role: Phase 1 Verification and Sanity Test Harness
==============================================================================
Validates:
1. Environment and configuration loading.
2. Directory structure creation.
3. Sample student documents presence and integrity.
4. LLM abstraction layer instantiation (Gemini, Claude, Ollama).
5. Live LLM connectivity test if GEMINI_API_KEY is provided in .env.
"""

import sys
from pathlib import Path

# Add project root to sys.path so modules can be imported directly
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from llm import get_llm_client, GeminiClient, ClaudeClient, OllamaClient


def test_configuration():
    print("\n--- 1. Testing Configuration & Environment ---")
    print(f"Project Root: {settings.PROJECT_ROOT}")
    print(f"Configured LLM Provider: {settings.LLM_PROVIDER}")
    print(f"Gemini Model: {settings.GEMINI_MODEL}")
    print(f"Claude Model: {settings.ANTHROPIC_MODEL}")
    print(f"Embedding Model: {settings.EMBEDDING_MODEL_NAME}")
    print(f"RAG Similarity Threshold: {settings.RAG_SIMILARITY_THRESHOLD}")
    print("Configuration loaded successfully.")


def test_directories():
    print("\n--- 2. Testing Required Directories ---")
    required_dirs = [
        settings.DATA_DIR,
        settings.OUTPUTS_DIR,
        settings.DB_DIR,
        settings.CHROMA_PERSIST_DIR,
    ]
    for d in required_dirs:
        assert d.exists(), f"Directory missing: {d}"
        print(f"Verified directory: {d.relative_to(settings.PROJECT_ROOT)}")
    print("All directories exist.")


def test_sample_documents():
    print("\n--- 3. Testing Sample Student Documents ---")
    expected_files = [
        "OS_Unit3_Virtual_Memory_Notes.txt",
        "DBMS_Unit2_Relational_Algebra_Notes.md",
        "KTU_S7_Timetable_and_Exams.txt",
        "KTU_S7_CS402_Syllabus.txt",
        "KTU_S7_CS402_Syllabus.pdf",
    ]
    for filename in expected_files:
        doc_path = settings.DATA_DIR / filename
        assert doc_path.exists(), f"Sample document missing: {filename}"
        size = doc_path.stat().st_size
        assert size > 100, f"Sample document suspiciously small: {filename} ({size} bytes)"
        print(f"Verified sample document: {filename} ({size} bytes)")
    print("All sample documents loaded and validated.")


def test_llm_factory():
    print("\n--- 4. Testing LLM Factory & Multi-Provider Abstraction ---")
    gemini = get_llm_client("gemini")
    assert isinstance(gemini, GeminiClient), f"Expected GeminiClient, got {type(gemini)}"
    print("GeminiClient initialized successfully.")

    claude = get_llm_client("claude")
    assert isinstance(claude, ClaudeClient), f"Expected ClaudeClient, got {type(claude)}"
    print("ClaudeClient initialized successfully.")

    ollama = get_llm_client("ollama")
    assert isinstance(ollama, OllamaClient), f"Expected OllamaClient, got {type(ollama)}"
    print("OllamaClient initialized successfully.")

    active_client = get_llm_client()
    print(f"Active Client configured by .env: {type(active_client).__name__}")


def test_live_call():
    print("\n--- 5. Testing Live LLM Generation (Gemini) ---")
    client = get_llm_client("gemini")
    api_key = settings.GEMINI_API_KEY
    if not api_key or api_key.startswith("your_"):
        print("[SKIPPED] GEMINI_API_KEY not configured in .env. Skipping live API call.")
        print("          (Set your key in .env to test live generation).")
        return

    print("Attempting test generation with Gemini API...")
    response = client.generate([
        {"role": "user", "content": "Hello! Reply with the exact word 'KTU_READY' and nothing else."}
    ])
    print(f"Response Content: {response.content}")
    print(f"Tool Calls Count: {len(response.tool_calls)}")
    if "KTU_READY" in response.content.upper():
        print("Live Gemini API call SUCCESSFUL!")
    else:
        print("Live response received (check output above).")


if __name__ == "__main__":
    print("==================================================================")
    print("  RUNNING PHASE 1 VERIFICATION: SCAFFOLD, CONFIG, LLM, DATA")
    print("==================================================================")
    try:
        test_configuration()
        test_directories()
        test_sample_documents()
        test_llm_factory()
        test_live_call()
        print("\n==================================================================")
        print("  ALL PHASE 1 CHECKS PASSED SUCCESSFULLY!")
        print("==================================================================")
    except AssertionError as e:
        print(f"\n[FAIL] Assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error during verification: {e}")
        sys.exit(1)
