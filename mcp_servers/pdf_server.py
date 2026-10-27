"""
==============================================================================
MCP Server: pdf_server.py
Domain: Document Generation & ReportLab PDF Compilation
Protocol: Model Context Protocol (FastMCP) over stdio
==============================================================================
Provides tools to generate formatted, academic-ready PDF documents:
- `generate_pdf`: Compiles structured study summaries, exam notes, or assignment
  reports into `outputs/` and returns the file path.

Features:
- Markdown Parsing: Converts markdown headers (`# `, `## `), bullet lists (`* `, `- `),
  and bold text (`**text**`) into ReportLab Flowables.
- Clean Academic Typography: Professional title headers, metadata timestamps,
  and page margins.
"""

from __future__ import annotations
import datetime
import html
import re
import time
from pathlib import Path
from typing import Any, Dict
from mcp.server.fastmcp import FastMCP
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from app.config import settings

mcp = FastMCP("pdf_server")

OUTPUTS_DIR = settings.OUTPUTS_DIR
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def format_inline_markdown(text: str) -> str:
    """Escapes HTML entities and converts safe markdown bold/italic tags for ReportLab."""
    safe = html.escape(text)
    # Convert **bold** to <b>bold</b>
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    # Convert *italic* or _italic_ to <i>italic</i> (ensuring no unmatched bullet tags)
    safe = re.sub(r"(?<!\w)\*([^\*]+?)\*(?!\w)", r"<i>\1</i>", safe)
    safe = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"<i>\1</i>", safe)
    return safe


def make_safe_paragraph(raw_text: str, style: Any) -> Paragraph:
    """Creates a ReportLab Paragraph with a fallback to plain text on XML parsing errors."""
    formatted = format_inline_markdown(raw_text)
    try:
        return Paragraph(formatted, style)
    except Exception:
        plain = html.escape(re.sub(r"[\*\_<>]", "", raw_text))
        return Paragraph(plain, style)


def parse_markdown_to_flowables(content: str, styles: Any) -> list:
    """
    Parses plain text with basic markdown formatting into ReportLab flowable elements.
    Supports:
      - Headings: # (Heading 1), ## (Heading 2), ### (Heading 3)
      - Bullet points: * or -
      - Paragraphs with bold (**text**)
    """
    flowables = []
    lines = content.split("\n")

    for line in lines:
        line_str = line.strip()
        if not line_str:
            flowables.append(Spacer(1, 6))
            continue

        # 1. Heading 1
        if line_str.startswith("# "):
            clean_text = line_str[2:].strip()
            flowables.append(Spacer(1, 10))
            flowables.append(make_safe_paragraph(clean_text, styles["Heading1"]))
            flowables.append(Spacer(1, 4))

        # 2. Heading 2
        elif line_str.startswith("## "):
            clean_text = line_str[3:].strip()
            flowables.append(Spacer(1, 8))
            flowables.append(make_safe_paragraph(clean_text, styles["Heading2"]))
            flowables.append(Spacer(1, 4))

        # 3. Heading 3
        elif line_str.startswith("### "):
            clean_text = line_str[4:].strip()
            flowables.append(Spacer(1, 6))
            flowables.append(make_safe_paragraph(clean_text, styles["Heading3"]))
            flowables.append(Spacer(1, 2))

        # 4. Bullet lists
        elif line_str.startswith(("- ", "* ")):
            clean_text = line_str[2:].strip()
            formatted_bullet = format_inline_markdown(clean_text)
            try:
                flowables.append(Paragraph(f"&bull; &nbsp; {formatted_bullet}", styles["Bullet"]))
            except Exception:
                plain = html.escape(re.sub(r"[\*\_<>]", "", clean_text))
                flowables.append(Paragraph(f"&bull; &nbsp; {plain}", styles["Bullet"]))
            flowables.append(Spacer(1, 2))

        # 5. Standard body paragraph
        else:
            flowables.append(make_safe_paragraph(line_str, styles["BodyText"]))
            flowables.append(Spacer(1, 4))

    return flowables


def cleanup_old_generated_pdfs(max_age_hours: int = 48) -> int:
    """
    Safely cleans up temporary generated PDFs older than the retention threshold.
    Returns the count of purged files.
    """
    purged = 0
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    try:
        for p in OUTPUTS_DIR.glob("*.pdf"):
            if p.is_file() and p.stat().st_mtime < cutoff:
                try:
                    p.unlink(missing_ok=True)
                    purged += 1
                except Exception:
                    pass
    except Exception:
        pass
    return purged


@mcp.tool()
def generate_pdf(
    title: str,
    content: str,
    filename: str,
) -> Dict[str, Any]:
    """
    Compiles text content into a formatted academic PDF document saved in outputs/.

    Args:
        title: Title of the document to be displayed at the top.
        content: Text or markdown content (supports headings #, ##, and bullets *, -).
        filename: Destination filename (e.g. "OS_Unit3_Summary.pdf").

    Returns:
        Dictionary with status, filename, download URL, and file size in bytes.
    """
    # Secure filename sanitization & path traversal prevention
    raw_name = Path(filename).name.strip()
    clean_filename = re.sub(r"[^\w\-.]", "_", raw_name)
    if not clean_filename.lower().endswith(".pdf"):
        clean_filename += ".pdf"

    pdf_path = (OUTPUTS_DIR / clean_filename).resolve()
    # Path traversal check
    if not str(pdf_path).startswith(str(OUTPUTS_DIR.resolve())):
        return {
            "status": "error",
            "action": "generate_pdf",
            "message": "Invalid filename: Path traversal detected.",
        }

    try:
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=letter,
            rightMargin=50,
            leftMargin=50,
            topMargin=50,
            bottomMargin=50,
        )

        styles = getSampleStyleSheet()

        # Custom typography styles
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Title"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1A365D"),
            spaceAfter=6,
            alignment=0,  # Left-aligned
        )

        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#718096"),
            spaceAfter=12,
        )

        styles["Heading1"].fontSize = 15
        styles["Heading1"].leading = 19
        styles["Heading1"].textColor = colors.HexColor("#2B6CB0")
        styles["Heading1"].spaceBefore = 10
        styles["Heading1"].spaceAfter = 4

        styles["Heading2"].fontSize = 12
        styles["Heading2"].leading = 16
        styles["Heading2"].textColor = colors.HexColor("#2D3748")
        styles["Heading2"].spaceBefore = 8
        styles["Heading2"].spaceAfter = 3

        styles["BodyText"].fontSize = 10
        styles["BodyText"].leading = 14
        styles["BodyText"].textColor = colors.HexColor("#2D3748")

        styles["Bullet"].fontSize = 10
        styles["Bullet"].leading = 14
        styles["Bullet"].leftIndent = 12

        story = []

        # Document Header
        safe_title = html.escape(title)
        story.append(Paragraph(safe_title, title_style))
        timestamp_str = datetime.datetime.now().strftime("%B %d, %Y - %I:%M %p")
        story.append(Paragraph(f"Generated by RAG-MCP Personal Assistant &bull; {timestamp_str}", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#E2E8F0"), spaceAfter=14))

        # Body Flowables
        body_flowables = parse_markdown_to_flowables(content, styles)
        story.extend(body_flowables)

        # Build PDF
        doc.build(story)

        # Strict validation: Check file existence, size, magic bytes (%PDF-), and readable structure
        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            pdf_path.unlink(missing_ok=True)
            return {
                "status": "error",
                "action": "generate_pdf",
                "message": "PDF compilation failed: Generated file is empty or was not created.",
            }

        file_size = pdf_path.stat().st_size
        with open(pdf_path, "rb") as f:
            header = f.read(5)
            f.seek(max(0, file_size - 1024))
            trailer = f.read()

        if header != b"%PDF-" or b"%%EOF" not in trailer:
            pdf_path.unlink(missing_ok=True)
            return {
                "status": "error",
                "action": "generate_pdf",
                "message": "PDF validation failed: Generated file does not contain a valid readable PDF signature.",
            }

        return {
            "status": "success",
            "action": "generate_pdf",
            "title": title,
            "filename": clean_filename,
            "file_path": str(pdf_path),
            "file_size_bytes": file_size,
            "download_url": f"/api/download/pdf/{clean_filename}",
            "message": f"Your PDF is ready.\n\n**{clean_filename}** — Download PDF",
        }

    except Exception as e:
        pdf_path.unlink(missing_ok=True)
        return {
            "status": "error",
            "action": "generate_pdf",
            "message": f"PDF compilation failed: {str(e)}",
        }


if __name__ == "__main__":
    mcp.run()
