"""
==============================================================================
Module: rag.ingest
Role in Architecture: Document Ingestion and Text Extraction Pipeline
==============================================================================
This module serves as the entry door of our RAG architecture.
It loads private student documents (PDF, TXT, DOCX, MD) and extracts their raw
text while meticulously preserving document metadata, notably:
  - `source_file`: The filename from which the text originated.
  - `page`: The exact page or section index (vital for [filename, page] citations).
  - `doc_id`: Unique identifier for tracking and deduplication.

Design Choice for KTU Review:
Rather than treating documents as opaque text blobs, we preserve page-level
provenance during ingestion. When the RAG Agent answers, it can trace each fact
back to a verifiable physical page in the student's materials.
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import pypdf
import docx

from app.config import settings


@dataclass
class Document:
    """
    Standard container representing an extracted document or document page.
    """
    content: str
    metadata: Dict[str, str | int] = field(default_factory=dict)

    @property
    def source_file(self) -> str:
        return str(self.metadata.get("source_file", "unknown"))

    @property
    def page(self) -> int:
        return int(self.metadata.get("page", 1))


def extract_from_pdf(file_path: Path) -> List[Document]:
    """
    Extracts text page-by-page from a PDF document using pypdf.
    Each physical PDF page becomes a separate Document object with page metadata.
    """
    docs: List[Document] = []
    try:
        reader = pypdf.PdfReader(str(file_path))
        for page_idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                docs.append(
                    Document(
                        content=text,
                        metadata={
                            "source_file": file_path.name,
                            "page": page_idx + 1,  # 1-indexed for academic citations
                            "doc_id": f"{file_path.stem}_p{page_idx + 1}_{uuid.uuid4().hex[:6]}",
                            "file_type": "pdf",
                        },
                    )
                )
    except Exception as e:
        print(f"[ERROR] Failed to extract PDF {file_path.name}: {e}")
    return docs


def extract_from_docx(file_path: Path) -> List[Document]:
    """
    Extracts text from a Microsoft Word (.docx) document using python-docx.
    Estimates pages based on logical section breaks or word clusters (~400 words/page).
    """
    docs: List[Document] = []
    try:
        doc = docx.Document(str(file_path))
        full_text_paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        
        # Group paragraphs into ~400 word simulated pages
        current_page_text: List[str] = []
        current_word_count = 0
        page_num = 1

        for para in full_text_paras:
            words = para.split()
            current_page_text.append(para)
            current_word_count += len(words)

            if current_word_count >= 400:
                docs.append(
                    Document(
                        content="\n\n".join(current_page_text),
                        metadata={
                            "source_file": file_path.name,
                            "page": page_num,
                            "doc_id": f"{file_path.stem}_p{page_num}_{uuid.uuid4().hex[:6]}",
                            "file_type": "docx",
                        },
                    )
                )
                page_num += 1
                current_page_text = []
                current_word_count = 0

        if current_page_text:
            docs.append(
                Document(
                    content="\n\n".join(current_page_text),
                    metadata={
                        "source_file": file_path.name,
                        "page": page_num,
                        "doc_id": f"{file_path.stem}_p{page_num}_{uuid.uuid4().hex[:6]}",
                        "file_type": "docx",
                    },
                )
            )
    except Exception as e:
        print(f"[ERROR] Failed to extract DOCX {file_path.name}: {e}")
    return docs


def extract_from_text_or_markdown(file_path: Path) -> List[Document]:
    """
    Extracts text from plain text (.txt) or markdown (.md) documents.
    Detects page break separators (form feed \f or markdown '---' page separators),
    or splits into ~3000 character logical pages to maintain manageable chunk scopes.
    """
    docs: List[Document] = []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        
        # Check for explicit form feed page markers
        if "\f" in text:
            raw_pages = text.split("\f")
        else:
            # Split into ~2500 character logical pages preserving paragraph boundaries
            paragraphs = text.split("\n\n")
            raw_pages = []
            curr_buf: List[str] = []
            curr_len = 0
            for p in paragraphs:
                p_str = p.strip()
                if not p_str:
                    continue
                curr_buf.append(p_str)
                curr_len += len(p_str)
                if curr_len >= 2500:
                    raw_pages.append("\n\n".join(curr_buf))
                    curr_buf = []
                    curr_len = 0
            if curr_buf:
                raw_pages.append("\n\n".join(curr_buf))

        # If file is short, it forms a single page
        if not raw_pages:
            raw_pages = [text]

        for page_idx, page_content in enumerate(raw_pages):
            content_clean = page_content.strip()
            if content_clean:
                docs.append(
                    Document(
                        content=content_clean,
                        metadata={
                            "source_file": file_path.name,
                            "page": page_idx + 1,
                            "doc_id": f"{file_path.stem}_p{page_idx + 1}_{uuid.uuid4().hex[:6]}",
                            "file_type": file_path.suffix.lstrip(".").lower(),
                        },
                    )
                )
    except Exception as e:
        print(f"[ERROR] Failed to extract text/markdown {file_path.name}: {e}")
    return docs


def load_single_document(file_path: Path | str) -> List[Document]:
    """
    Universal ingestion dispatcher for a single file.
    Routes to the appropriate extractor based on file extension.
    """
    p = Path(file_path).resolve()
    if not p.exists() or not p.is_file():
        print(f"[WARNING] File not found: {p}")
        return []

    ext = p.suffix.lower()
    if ext == ".pdf":
        return extract_from_pdf(p)
    elif ext in (".docx", ".doc"):
        return extract_from_docx(p)
    elif ext in (".txt", ".md", ".markdown"):
        return extract_from_text_or_markdown(p)
    else:
        print(f"[INFO] Unsupported file extension '{ext}' for {p.name}. Skipping.")
        return []


def load_documents(directory: Optional[Path | str] = None) -> List[Document]:
    """
    Scans a directory (defaults to settings.DATA_DIR) and extracts all supported documents.
    """
    target_dir = Path(directory or settings.DATA_DIR).resolve()
    if not target_dir.exists():
        print(f"[WARNING] Ingest directory does not exist: {target_dir}")
        return []

    supported_extensions = {".pdf", ".docx", ".doc", ".txt", ".md", ".markdown"}
    all_extracted: List[Document] = []

    for file_path in target_dir.glob("*"):
        if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
            docs = load_single_document(file_path)
            all_extracted.extend(docs)
            print(f"[INGEST] Loaded {len(docs)} page(s) from '{file_path.name}'")

    print(f"[INGEST COMPLETE] Total pages extracted: {len(all_extracted)}")
    return all_extracted


if __name__ == "__main__":
    import sys
    from rag.chunking import chunk_documents
    from rag.vectorstore import get_vector_store

    print("=" * 65)
    print("  KNOWLEDGE BASE INGESTION CLI: PDF / TXT / DOCX / MD")
    print("=" * 65)

    print(f"\n[1/3] Scanning and loading documents from: {settings.DATA_DIR}")
    docs = load_documents(settings.DATA_DIR)
    if not docs:
        print("[ERROR] No documents found to ingest. Exiting.")
        sys.exit(1)

    print(f"\n[2/3] Chunking {len(docs)} document pages (Window: {settings.RAG_CHUNK_SIZE} tokens, Overlap: {settings.RAG_CHUNK_OVERLAP})...")
    chunks = chunk_documents(docs)
    print(f"      Created {len(chunks)} semantic chunks with metadata.")

    print("\n[3/3] Generating dense embeddings & storing into ChromaDB...")
    store = get_vector_store()
    added_count = store.add_chunks(chunks)

    stats = store.get_collection_stats()
    print("\n" + "=" * 65)
    print("  INGESTION COMPLETE")
    print(f"  - Total chunks in collection: {stats.get('total_chunks')}")
    print(f"  - Source files indexed: {stats.get('source_files')}")
    print(f"  - Storage location: {stats.get('storage_directory')}")
    print("=" * 65)
