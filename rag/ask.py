"""
==============================================================================
Module: rag.ask
Role in Architecture: Command-Line RAG Question Answering Interface
==============================================================================
Allows quick, standalone testing of the entire RAG pipeline from the terminal
without booting up the full Streamlit UI or FastAPI server.

Usage:
  python -m rag.ask "What topics are covered in Unit 3 of OS?"
  python -m rag.ask "When is my CS402 internal exam?"
  python -m rag.ask "Who won the 2018 FIFA World Cup?"
"""

from __future__ import annotations
import sys
from app.config import settings
from rag.generator import get_rag_generator


def main():
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        print("\nEnter your question (or type 'exit'):")
        query = input("> ").strip()
        if not query or query.lower() in ("exit", "quit"):
            return

    print("\n" + "=" * 65)
    print(f" QUESTION: {query}")
    print("=" * 65)

    generator = get_rag_generator()
    print("[RAG] Retrieving candidate chunks from ChromaDB...")
    response = generator.answer_question(query)

    print("\n" + "-" * 65)
    print(" ANSWER:")
    print("-" * 65)
    print(response.answer)

    print("\n" + "-" * 65)
    print(" CITATIONS:")
    print("-" * 65)
    if response.citations:
        for c in response.citations:
            print(f"  * {c}")
    else:
        print("  (No citations - Refusal triggered or no source found)")

    print("\n" + "-" * 65)
    print(" RETRIEVAL TELEMETRY (DEBUG TRACE):")
    print("-" * 65)
    print(f"  * Max Cosine Similarity: {response.max_similarity:.4f}")
    print(f"  * Threshold Applied:     {settings.RAG_SIMILARITY_THRESHOLD}")
    print(f"  * Refusal Triggered:     {response.refused}")
    print(f"  * Retrieved Chunks Count:{len(response.retrieved_chunks)}")

    for idx, c in enumerate(response.retrieved_chunks, 1):
        print(f"\n  [Chunk {idx}] ID: {c['chunk_id']} | Sim: {c['similarity']} | Source: {c['source_file']} (Page {c['page']})")
        preview = c['text'].replace('\n', ' ')[:140]
        print(f"    Preview: \"{preview}...\"")

    print("\n" + "=" * 65)


if __name__ == "__main__":
    main()
