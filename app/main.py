"""
==============================================================================
Module: app.main
Role in Architecture: FastAPI Backend Application Entry Point
==============================================================================
Serves the REST API for the RAG & MCP Multi-Agent Personal Assistant.
Enables asynchronous request handling, CORS for the Streamlit UI,
and static file serving for generated outputs (PDFs, .ics files).

Run locally:
  uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
"""

from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for FastAPI startup and shutdown."""
    print("=" * 65)
    print("  FASTAPI BACKEND STARTING: RAG & MCP MULTI-AGENT ASSISTANT")
    print(f"  * Project Root:    {settings.PROJECT_ROOT}")
    print(f"  * Configured LLM:  {settings.LLM_PROVIDER} ({settings.GEMINI_MODEL})")
    print(f"  * ChromaDB Path:   {settings.CHROMA_PERSIST_DIR}")
    print("=" * 65)
    yield
    print("[FASTAPI SHUTDOWN] Backend services stopped.")


# Initialize FastAPI App
app = FastAPI(
    title="RAG & MCP Multi-Agent Personal Assistant API",
    description="Backend REST API for University Student Assistant Architecture",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Streamlit and external frontend connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Router
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint for container probes and UI connectivity tests."""
    return {
        "status": "healthy",
        "service": "rag-mcp-assistant",
        "llm_provider": settings.LLM_PROVIDER,
        "model": settings.GEMINI_MODEL,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
