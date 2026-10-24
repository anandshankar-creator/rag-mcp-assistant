"""
==============================================================================
Module: app.routes
Role in Architecture: FastAPI REST API Endpoints & Request Handlers
==============================================================================
Defines the client-server boundary for the Personal Assistant:
- `POST /api/chat`: Invokes the LangGraph state machine, returns grounded answer,
  citations, action receipts, and execution trace.
- `POST /api/upload`: Handles real-time document upload (PDF, DOCX, TXT, MD),
  chunks the file, embeds with sentence-transformers, and updates ChromaDB.
- `GET /api/documents`: Lists all indexed documents in the knowledge base.
- `DELETE /api/documents/{filename}`: Removes a document from disk and vector store.
- `POST /api/confirm-action`: Human-in-the-Loop execution gate for email/actions.
- `GET /api/preferences` & `POST /api/preferences`: Student user profile settings.
"""

from __future__ import annotations
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.config import settings
from agents.graph import run_assistant
from agents.memory import ConversationMemory
from rag.ingest import load_single_document
from rag.chunking import chunk_documents
from rag.vectorstore import get_vector_store
from mcp_servers.client import get_mcp_client

router = APIRouter(prefix="/api")


# --- Pydantic Request & Response Schemas ---

class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's message or instruction")
    session_id: str = Field(default="default_student", description="Conversation session ID")


class ChatResponse(BaseModel):
    session_id: str
    response: str
    route: str
    route_reasoning: str
    citations: List[str]
    action_receipts: List[Dict[str, Any]]
    trace: List[Dict[str, Any]]


class ActionConfirmRequest(BaseModel):
    action_type: str = Field(..., description="Name of the action (e.g. 'send_email')")
    parameters: Dict[str, Any] = Field(..., description="Approved arguments for the tool")


class PreferencesUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    default_reminder_lead_hours: Optional[int] = None


# --- Endpoints ---

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """
    Main conversational endpoint:
    Dispatches request to the LangGraph Multi-Agent Orchestrator.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        final_state = run_assistant(user_message=req.message, session_id=req.session_id)
        return ChatResponse(
            session_id=req.session_id,
            response=final_state.get("final_response", ""),
            route=final_state.get("route", "CHAT"),
            route_reasoning=final_state.get("route_reasoning", ""),
            citations=final_state.get("citations", []),
            action_receipts=final_state.get("action_receipts", []),
            trace=final_state.get("trace", []),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assistant processing failed: {str(e)}")


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Uploads a new personal document (PDF, TXT, DOCX, MD), chunks it,
    and indexes it directly into ChromaDB.
    """
    supported_extensions = {".pdf", ".docx", ".doc", ".txt", ".md", ".markdown"}
    ext = Path(file.filename).suffix.lower()

    if ext not in supported_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Supported: {', '.join(supported_extensions)}",
        )

    # Save file into data/documents/
    dest_path = settings.DATA_DIR / file.filename
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Ingest and chunk
    try:
        docs = load_single_document(dest_path)
        chunks = chunk_documents(docs)
        store = get_vector_store()
        # Delete existing chunks if re-uploading the same file
        store.delete_document(file.filename)
        added_count = store.add_chunks(chunks)

        return {
            "status": "success",
            "filename": file.filename,
            "pages_extracted": len(docs),
            "chunks_created": added_count,
            "message": f"Successfully indexed '{file.filename}' ({added_count} chunks).",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.get("/documents")
async def list_documents():
    """
    Lists all documents currently stored on disk and indexed in ChromaDB.
    """
    store = get_vector_store()
    stats = store.get_collection_stats()

    # Get files on disk
    files_on_disk = []
    if settings.DATA_DIR.exists():
        for p in settings.DATA_DIR.glob("*"):
            if p.is_file() and not p.name.startswith("."):
                files_on_disk.append({
                    "filename": p.name,
                    "size_bytes": p.stat().st_size,
                    "indexed": p.name in stats.get("source_files", []),
                })

    return {
        "total_chunks": stats.get("total_chunks", 0),
        "documents": files_on_disk,
    }


@router.delete("/documents/{filename}")
async def delete_document(filename: str):
    """
    Removes a document from both disk and the ChromaDB vector store.
    """
    store = get_vector_store()
    deleted_chunks = store.delete_document(filename)

    file_path = settings.DATA_DIR / filename
    if file_path.exists():
        file_path.unlink()

    return {
        "status": "success",
        "filename": filename,
        "deleted_chunks": deleted_chunks,
        "message": f"Document '{filename}' deleted from knowledge base.",
    }


@router.post("/confirm-action")
async def confirm_action(req: ActionConfirmRequest):
    """
    Human-in-the-Loop Confirmation Gate:
    Explicitly executes a sensitive tool (such as email dispatch) after user approves in UI.
    """
    mcp_client = get_mcp_client()
    if not mcp_client.has_tool(req.action_type):
        raise HTTPException(status_code=400, detail=f"Tool '{req.action_type}' not found.")

    res = mcp_client.execute_tool(req.action_type, req.parameters)
    return res


@router.get("/preferences")
async def get_preferences():
    """Returns stored student preferences."""
    return ConversationMemory.get_all_preferences()


@router.post("/preferences")
async def update_preferences(prefs: PreferencesUpdate):
    """Updates student profile preferences in SQLite."""
    if prefs.name:
        ConversationMemory.set_preference("name", prefs.name)
    if prefs.email:
        ConversationMemory.set_preference("email", prefs.email)
    if prefs.default_reminder_lead_hours is not None:
        ConversationMemory.set_preference("default_reminder_lead_hours", str(prefs.default_reminder_lead_hours))

    return {"status": "success", "preferences": ConversationMemory.get_all_preferences()}
