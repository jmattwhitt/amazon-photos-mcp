"""File upload tools."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from amazon_photos_mcp import _get_client, _tool, _tool_annotations, mcp


@mcp.tool(annotations=_tool_annotations("upload_file"))
@_tool
def upload_file(file_path: str) -> dict[str, Any]:
    """Upload a single file to Amazon Photos. Deduplicates by MD5."""
    path = Path(file_path)
    if not path.exists():
        return {"error": True, "code": "NOT_FOUND", "message": f"File not found: {file_path}"}
    if not path.is_file():
        return {"error": True, "code": "INVALID_INPUT", "message": f"Not a file: {file_path}"}

    ap = _get_client()
    tmp_dir = tempfile.mkdtemp(prefix="ap_upload_")
    try:
        dest = os.path.join(tmp_dir, path.name)
        if sys.platform != "win32":
            try:
                # Try hard linking first to avoid duplicating large files on disk
                os.link(str(path), dest)
            except OSError:
                # Fall back to copying if cross-device link or other error
                shutil.copy2(str(path), dest)
        else:
            # Windows: os.link requires admin; skip straight to copy
            shutil.copy2(str(path), dest)
        result = ap.upload(tmp_dir)
        return {
            "status": "ok",
            "action": "uploaded",
            "file": path.name,
            "results": result if isinstance(result, list) else str(result),
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@mcp.tool(annotations=_tool_annotations("upload_folder"))
@_tool
def upload_folder(folder_path: str) -> dict[str, Any]:
    """Upload all photos/videos in a folder to Amazon Photos (recursive). Deduplicates by MD5."""
    path = Path(folder_path)
    if not path.exists():
        return {"error": True, "code": "NOT_FOUND", "message": f"Folder not found: {folder_path}"}
    if not path.is_dir():
        return {"error": True, "code": "INVALID_INPUT", "message": f"Not a folder: {folder_path}"}

    ap = _get_client()
    result = ap.upload(str(path))
    count = len(result) if isinstance(result, list) else None
    return {
        "status": "ok",
        "action": "uploaded",
        "folder": str(path),
        "files_processed": count,
        "results": result if isinstance(result, list) else str(result),
    }
