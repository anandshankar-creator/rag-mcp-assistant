"""
==============================================================================
Module: app.routes
Role in Architecture: Protected FastAPI REST API Endpoints & Request Handlers
==============================================================================
Defines the client-server boundary for the Personal Assistant with strict
Administrator-Only Authentication:
- `POST /api/auth/login`: Administrator login returning signed JWT access token.
- `POST /api/auth/logout`: Revokes current session token and invalidates access.
- `POST /api/auth/forgot-password`: Generates single-use reset token and emails link.
- `POST /api/auth/reset-password`: Validates reset token and sets new password.
- `GET /api/auth/verify`: Verifies active session token validity.
- `POST /api/chat`: Invokes LangGraph assistant (Protected).
- `POST /api/upload`: Chunks, embeds, and indexes document into ChromaDB (Protected).
- `GET /api/documents`: Lists indexed documents (Protected).
- `DELETE /api/documents/{filename}`: Removes document from disk and ChromaDB (Protected).
- `POST /api/confirm-action`: Human-in-the-Loop tool execution gate (Protected).
- `GET /api/preferences` & `POST /api/preferences`: Student user profile settings (Protected).
- `GET /api/download/pdf/{filename}`: Validated PDF download endpoint (Protected).
==============================================================================
"""

from __future__ import annotations
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.auth import (
    authenticate_administrator,
    check_reset_request_rate_limit,
    generate_password_reset_token,
    reset_password_with_token,
    revoke_token,
    verify_access_token,
    AuthError,
)
from app.auth_email import send_password_reset_email
from agents.graph import run_assistant
from agents.memory import ConversationMemory
from rag.ingest import load_single_document
from rag.chunking import chunk_documents
from rag.vectorstore import get_vector_store
from mcp_servers.client import get_mcp_client

router = APIRouter(prefix="/api")


# --- Authentication Dependency ---

async def get_current_admin(
    request: Request,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Enforces Administrator-only authentication:
    Accepts access token via standard 'Authorization: Bearer <token>' header
    or '?token=<token>' query parameter (supported for file download requests).
    """
    raw_token = None
    if authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization[7:].strip()
    elif token:
        raw_token = token.strip()

    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required: No authorization token provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_access_token(raw_token)
        return payload
    except AuthError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Authentication failed: Invalid or expired session token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# --- Pydantic Request & Response Schemas ---

class LoginRequest(BaseModel):
    email: str = Field(..., description="Administrator email address")
    password: str = Field(..., description="Administrator password")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    admin_email: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., description="Administrator email address")


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., description="Raw password reset token received via email")
    new_password: str = Field(..., description="New password adhering to complexity policy")


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
    origin: Optional[str] = Field(default=None, description="Source origin: LOCAL, WEB, NOT_FOUND, UNGROUNDED_CHAT, or ACTION")
    source_type: Optional[str] = Field(default=None, description="Underlying retrieval/action mechanism")
    urls: Optional[List[str]] = Field(default_factory=list, description="Verified web source URLs")
    tiers: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Domain authority credibility tiers")
    verified_quotes: Optional[List[str]] = Field(default_factory=list, description="Direct quotes verified in source page text")
    decision_path: Optional[str] = Field(default=None, description="Detailed QA routing and fallback decision path")


class ActionConfirmRequest(BaseModel):
    action_type: str = Field(..., description="Name of the action (e.g. 'send_email')")
    parameters: Dict[str, Any] = Field(..., description="Approved arguments for the tool")


class PreferencesUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    default_reminder_lead_hours: Optional[int] = None


# --- Authentication Endpoints ---

@router.post("/auth/login", response_model=LoginResponse)
async def login_endpoint(req: LoginRequest, request: Request):
    """
    Administrator Sign-In:
    Validates email and salted bcrypt password hash.
    Enforces progressive brute-force lockout.
    """
    client_ip = request.client.host if request.client else "unknown"
    try:
        res = authenticate_administrator(req.email, req.password, client_id=client_ip)
        return LoginResponse(**res)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/auth/logout")
async def logout_endpoint(
    request: Request,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    _admin: Dict[str, Any] = Depends(get_current_admin),
):
    """
    Administrator Sign-Out:
    Revokes the current session token so it cannot be used again.
    """
    raw_token = None
    if authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization[7:].strip()
    elif token:
        raw_token = token.strip()

    if raw_token:
        revoke_token(raw_token)

    return {"status": "success", "message": "Successfully logged out. Session invalidated."}


@router.post("/auth/forgot-password")
async def forgot_password_endpoint(req: ForgotPasswordRequest, request: Request):
    """
    Password Recovery Initiator:
    - Generates cryptographically secure, single-use token (stores only SHA-256 hash)
    - Enforces rate limiting
    - Dispatches reset link via dedicated email dispatcher
    - Returns generic confirmation message regardless of whether the email exists
    """
    client_ip = request.client.host if request.client else "unknown"
    allowed, rate_msg = check_reset_request_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail=rate_msg)

    # Generate token if matches admin email
    raw_token = generate_password_reset_token(req.email)
    if raw_token:
        try:
            send_password_reset_email(req.email, raw_token)
        except Exception as e:
            print(f"[AUTH ROUTE] Password reset email dispatch failed: {e}")

    # Constant generic response to prevent email enumeration
    return {
        "status": "success",
        "message": "If the email address matches our administrator records, a password reset link has been sent.",
    }


@router.post("/auth/reset-password")
async def reset_password_endpoint(req: ResetPasswordRequest):
    """
    Password Reset Completion:
    Validates single-use token, checks complexity policy, updates bcrypt hash,
    and invalidates all existing active sessions.
    """
    success, msg = reset_password_with_token(req.token, req.new_password)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    return {"status": "success", "message": msg}


@router.get("/auth/verify")
async def verify_auth_endpoint(admin: Dict[str, Any] = Depends(get_current_admin)):
    """Verifies that the provided token is active and valid."""
    return {"status": "authenticated", "admin_email": admin.get("sub")}


# --- Protected Application Endpoints ---

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, _admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Main conversational endpoint:
    Protected: Only authenticated administrator can converse with the assistant.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        final_state = run_assistant(user_message=req.message, session_id=req.session_id)
        route = final_state.get("route", "CHAT")
        default_origin = "UNGROUNDED_CHAT" if route == "CHAT" else ("ACTION" if route in ("ACTION", "CHAINED") else "LOCAL")
        default_source = "chat" if route == "CHAT" else ("action" if route in ("ACTION", "CHAINED") else "local_rag")
        return ChatResponse(
            session_id=req.session_id,
            response=final_state.get("final_response", ""),
            route=route,
            route_reasoning=final_state.get("route_reasoning", ""),
            citations=final_state.get("citations", []),
            action_receipts=final_state.get("action_receipts", []),
            trace=final_state.get("trace", []),
            origin=final_state.get("origin") or default_origin,
            source_type=final_state.get("source_type") or default_source,
            urls=final_state.get("urls", []),
            tiers=final_state.get("tiers", []),
            verified_quotes=final_state.get("verified_quotes", []),
            decision_path=final_state.get("decision_path"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assistant processing failed: {str(e)}")


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    _admin: Dict[str, Any] = Depends(get_current_admin),
):
    """
    Protected: Uploads a personal document, chunks it, and indexes it into ChromaDB.
    """
    supported_extensions = {".pdf", ".docx", ".doc", ".txt", ".md", ".markdown"}
    ext = Path(file.filename).suffix.lower()

    if ext not in supported_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Supported: {', '.join(supported_extensions)}",
        )

    dest_path = settings.DATA_DIR / file.filename
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    try:
        docs = load_single_document(dest_path)
        chunks = chunk_documents(docs)
        store = get_vector_store()
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
async def list_documents(_admin: Dict[str, Any] = Depends(get_current_admin)):
    """
    Protected: Lists all documents currently indexed in ChromaDB and on disk.
    """
    store = get_vector_store()
    stats = store.get_collection_stats()

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
async def delete_document(
    filename: str,
    _admin: Dict[str, Any] = Depends(get_current_admin),
):
    """
    Protected: Removes a document from disk and ChromaDB.
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
async def confirm_action(
    req: ActionConfirmRequest,
    _admin: Dict[str, Any] = Depends(get_current_admin),
):
    """
    Protected: Human-in-the-Loop Confirmation Gate.
    Unauthenticated users cannot execute MCP actions directly.
    """
    mcp_client = get_mcp_client()
    if not mcp_client.has_tool(req.action_type):
        raise HTTPException(status_code=400, detail=f"Tool '{req.action_type}' not found.")

    res = mcp_client.execute_tool(req.action_type, req.parameters)
    return res


@router.get("/preferences")
async def get_preferences(_admin: Dict[str, Any] = Depends(get_current_admin)):
    """Protected: Returns stored student preferences."""
    return ConversationMemory.get_all_preferences()


@router.post("/preferences")
async def update_preferences(
    prefs: PreferencesUpdate,
    _admin: Dict[str, Any] = Depends(get_current_admin),
):
    """Protected: Updates student profile preferences."""
    if prefs.name:
        ConversationMemory.set_preference("name", prefs.name)
    if prefs.email:
        ConversationMemory.set_preference("email", prefs.email)
    if prefs.default_reminder_lead_hours is not None:
        ConversationMemory.set_preference("default_reminder_lead_hours", str(prefs.default_reminder_lead_hours))

    return {"status": "success", "preferences": ConversationMemory.get_all_preferences()}


@router.get("/download/pdf/{filename}")
async def download_pdf_endpoint(
    filename: str,
    _admin: Dict[str, Any] = Depends(get_current_admin),
):
    """
    Protected: Secure PDF download endpoint for authenticated users.
    - Requires valid admin authentication token
    - Path traversal prevention
    - File existence & non-empty validation
    - Magic bytes signature check (%PDF-)
    - Clean attachment response with Content-Disposition
    """
    safe_filename = Path(filename).name.strip()
    if not safe_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF downloads are supported.")

    target_path = (settings.OUTPUTS_DIR / safe_filename).resolve()
    if not str(target_path).startswith(str(settings.OUTPUTS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Access denied: Path traversal detected.")

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"PDF '{safe_filename}' not found or is no longer available.")

    if target_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail=f"PDF '{safe_filename}' is empty or invalid.")

    try:
        with open(target_path, "rb") as f:
            if f.read(5) != b"%PDF-":
                raise HTTPException(status_code=400, detail="The requested file is not a valid PDF document.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    return FileResponse(
        path=str(target_path),
        media_type="application/pdf",
        filename=safe_filename,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "Cache-Control": "no-cache",
        },
    )
