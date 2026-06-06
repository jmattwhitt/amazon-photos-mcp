"""Photo/video media tools: URL retrieval, EXIF data, download, thumbnails, progress."""

from __future__ import annotations

import base64
import io as stdlib_io
import json
import os
import time
from pathlib import Path
from typing import Any

from amazon_photos_mcp import (
    PIPELINE_DEFAULT_DIR,
    _get_client,
    _safe_df_to_list,
    _tool,
    _tool_annotations,
    mcp,
)


@mcp.tool(annotations=_tool_annotations("get_photo_url"))
@_tool
def get_photo_url(node_id: str) -> dict[str, Any]:
    """Get the direct download URL for a photo/video by node ID."""
    ap = _get_client()
    result = ap.get_file(node_id)
    url = None
    if hasattr(result, "json"):
        data = result.json()
        url = (
            data.get("tempLink")
            or data.get("contentUrl")
            or data.get("url")
        )
    return {
        "node_id": node_id,
        "url": url,
        "raw": str(result)[:500] if url is None else None,
    }


@mcp.tool(annotations=_tool_annotations("get_exif_data"))
@_tool
def get_exif_data(node_id: str) -> dict[str, Any]:
    """Get EXIF metadata for a photo by node ID. Falls back to local parquet DB if API doesn't expose EXIF."""
    from amazon_photos_mcp import _clean_row

    ap = _get_client()

    try:
        result = ap.get_file(node_id)
        if hasattr(result, "json"):
            data = result.json()
            exif: dict[str, Any] = {}
            for section in ("image", "video", "exifData", "media"):
                if section in data:
                    exif.update(data[section])
            if exif:
                return {"node_id": node_id, "source": "api", "exif": exif}
    except Exception:
        pass

    db = ap.db
    if db is not None and "id" in db.columns:
        rows = db[db["id"] == node_id]
        if not rows.empty:
            row = _clean_row(rows.iloc[0].to_dict())
            exif_keys = [k for k in row if any(
                prefix in k.lower()
                for prefix in ("image.", "camera", "exif", "gps", "iso", "exposure", "aperture", "focal")
            )]
            return {
                "node_id": node_id,
                "source": "local_db",
                "exif": {k: row[k] for k in exif_keys if row.get(k) is not None},
                "note": "Upstream library did not return EXIF via API; showing indexed fields from local cache.",
            }

    return {"node_id": node_id, "exif": {}, "note": "No EXIF data found."}


@mcp.tool(annotations=_tool_annotations("get_thumbnail"))
@_tool
def get_thumbnail(node_id: str, max_size: int = 0) -> dict[str, Any]:
    """Get a base64-encoded thumbnail/preview of a photo for visual browsing.

    Downloads the full image from Amazon Photos, resizes it via PIL,
    and returns a base64-encoded JPEG. Falls back to just the URL on failure.

    Args:
        node_id: Amazon Photos node ID
        max_size: Maximum dimension (width or height) in pixels. Default 0 = use
                  thumbnail_max_size from config (defaults to 400).
    """
    from amazon_photos_mcp.config import get_config

    if max_size <= 0:
        max_size = int(get_config("thumbnail_max_size", default=400))
    import httpx

    ap = _get_client()
    result = ap.get_file(node_id)
    url = None

    if hasattr(result, "json"):
        data = result.json()
        url = data.get("tempLink") or data.get("contentUrl") or data.get("url")

    if not url:
        return {"node_id": node_id, "thumbnail": None, "error": "Could not resolve download URL."}

    try:
        http_client = getattr(ap, "client", None)
        s = http_client if http_client is not None else httpx.Client()

        with s.stream("GET", url, timeout=30) as r:
            r.raise_for_status()

            ctype = r.headers.get("Content-Type", "")
            if "video" in ctype:
                return {
                    "node_id": node_id,
                    "thumbnail_base64": None,
                    "url": url,
                    "fallback": "Cannot generate thumbnail for video files. Use the URL to view.",
                }

            size_limit = 50 * 1024 * 1024  # 50 MB
            content = r.read()
            if len(content) > size_limit:
                return {
                    "node_id": node_id,
                    "thumbnail_base64": None,
                    "url": url,
                    "fallback": (
                        f"Image too large to generate thumbnail "
                        f"({len(content) / 1024 / 1024:.1f} MB). Use the URL to view."
                    ),
                }

        from PIL import Image

        img = Image.open(stdlib_io.BytesIO(content))
        img.thumbnail((max_size, max_size), Image.LANCZOS)

        buf = stdlib_io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        return {
            "node_id": node_id,
            "thumbnail_base64": b64,
            "format": "jpeg",
            "mime_type": "image/jpeg",
            "size_bytes": len(buf.getvalue()),
            "dimensions": {"width": img.width, "height": img.height},
            "url": url,
        }
    except Exception as e:
        return {
            "node_id": node_id,
            "thumbnail_base64": None,
            "url": url,
            "fallback": "Thumbnail generation failed. Use the URL to view/download the image.",
            "error": str(e),
        }


@mcp.tool(annotations=_tool_annotations("get_download_progress"))
@_tool
def get_download_progress() -> dict[str, Any]:
    """Check progress of an ongoing download_library operation.

    Reads the progress file written by download_library (if progress_file param was given).
    Returns current batch, percent complete, and elapsed time.
    """
    progress_path = os.environ.get("AMAZON_PHOTOS_DOWNLOAD_PROGRESS", "")
    if not progress_path:
        return {
            "status": "not_configured",
            "message": (
                "No progress file configured. "
                "Set AMAZON_PHOTOS_DOWNLOAD_PROGRESS env var "
                "or pass progress_file to download_library."
            ),
        }
    p = Path(progress_path)
    if not p.exists():
        return {"status": "no_progress", "message": "No progress file found. No download in progress?"}
    try:
        data = json.loads(p.read_text())
        return {"status": "in_progress", **data}
    except Exception:
        return {"status": "error", "message": "Could not read progress file."}


@mcp.tool(annotations=_tool_annotations("download"))
@_tool
def download(
    node_ids: list[str] | None = None,
    query: str = "",
    year: int | None = None,
    month: int | None = None,
    day: int | None = None,
    media_type: str = "PHOTOS",
    output_dir: str = "",
    max_items: int = 500,
) -> dict[str, Any]:
    """Download photos/videos from Amazon Photos.

    Can download by node IDs, by search query, or by date range.
    One of node_ids, query, or year must be provided.

    Args:
        node_ids: Specific node IDs to download
        query: Amazon Photos query string (e.g., "type:(PHOTOS) AND things:(beach)")
        year: Year filter (requires at least year, optionally month/day)
        month: Month filter (1-12)
        day: Day filter (1-31)
        media_type: "PHOTOS" or "VIDEOS"
        output_dir: Custom output directory (auto-generated if empty)
        max_items: Maximum items to download (capped at 2000)
    """
    ap = _get_client()

    # Resolve what to download
    if node_ids is not None:
        ids = node_ids
        if not output_dir:
            output_dir = str(Path.home() / "Downloads" / "amazon-photos")
    elif year is not None:
        parts = [f"type:({media_type})", f"timeYear:({year})"]
        if month:
            parts.append(f"timeMonth:({month})")
        if day:
            parts.append(f"timeDay:({day})")
        df = ap.query(" ".join(parts))
        items = _safe_df_to_list(df, min(max_items, 2000))
        if not items:
            return {"status": "no_results", "query": " ".join(parts), "count": 0, "node_ids": []}
        ids = [item["id"] for item in items if item.get("id")]
        if not output_dir:
            date_str = f"{year:04d}" + (f"-{month:02d}" if month else "") + (f"-{day:02d}" if day else "")
            output_dir = str(Path.home() / "Downloads" / "amazon-photos" / date_str)
    elif query:
        df = ap.query(query)
        items = _safe_df_to_list(df, min(max_items, 2000))
        if not items:
            return {"status": "no_results", "query": query, "count": 0, "node_ids": []}
        ids = [item["id"] for item in items if item.get("id")]
        if not output_dir:
            slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in query)[:40]
            output_dir = str(Path(PIPELINE_DEFAULT_DIR) / slug / "raw")
    else:
        return {
            "error": True,
            "code": "INVALID_ARGS",
            "message": "Provide node_ids, query, or year to specify what to download.",
        }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    ap.download(ids, out=str(out))

    return {
        "status": "ok",
        "action": "downloaded",
        "downloaded": len(ids),
        "output_dir": str(out),
        "node_ids": ids,
    }


@mcp.tool(annotations=_tool_annotations("download_library"))
@_tool
def download_library(
    output_dir: str = "",
    media_type: str = "PHOTOS",
    max_items: int = 5000,
    organize_by: str = "year_month",
    progress_file: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Download your entire Amazon Photos library for backup or migration.

    Organizes photos into subdirectories by date for easy import into
    Immich, PhotoPrism, or other self-hosted solutions.

    Args:
        output_dir: Root directory for downloads. Defaults to ~/Downloads/amazon-photos-export/
        media_type: "PHOTOS" or "VIDEOS"
        max_items: Maximum total items to download (capped at 10000)
        organize_by: "year_month" (2024/01/) or "flat" (single directory)
        progress_file: Path to write JSON progress updates for get_download_progress
        dry_run: If True, count items without downloading anything
    """
    ap = _get_client()
    max_items = min(max_items, 10000)
    start_time = time.monotonic()

    if not output_dir:
        output_dir = str(Path.home() / "Downloads" / "amazon-photos-export")

    # Resolve progress file path
    progress_path: Path | None = None
    if progress_file:
        progress_path = Path(progress_file)
    elif os.environ.get("AMAZON_PHOTOS_DOWNLOAD_PROGRESS"):
        progress_path = Path(os.environ["AMAZON_PHOTOS_DOWNLOAD_PROGRESS"])

    # Get all items
    if media_type == "VIDEOS":
        df = ap.videos()
    else:
        df = ap.photos()

    if df is None or (hasattr(df, "empty") and df.empty):
        return {"status": "no_data", "message": f"No {media_type.lower()} found in library."}

    items = _safe_df_to_list(df, max_items)
    if not items:
        return {"status": "no_items", "message": "No items after processing."}

    node_ids = [item["id"] for item in items if item.get("id")]

    if dry_run:
        # Estimate sizes
        from amazon_photos_mcp import _is_nan

        total_size = 0
        for item in items:
            s = item.get("size")
            if s is not None and not _is_nan(s):
                try:
                    total_size += int(s)
                except (TypeError, ValueError):
                    pass
        return {
            "status": "dry_run",
            "total_items": len(node_ids),
            "estimated_size_bytes": total_size,
            "estimated_size_gb": round(total_size / (1024 ** 3), 2) if total_size else "unknown",
            "output_dir": output_dir,
            "organize_by": organize_by,
            "message": f"Would download {len(node_ids)} {media_type.lower()} items. Set dry_run=False to execute.",
        }

    out = Path(output_dir)
    total = len(node_ids)

    # Download in batches with per-date subdirectories
    batch_size = 200
    downloaded = 0
    failed: list[str] = []
    num_batches = (total + batch_size - 1) // batch_size

    for batch_idx, i in enumerate(range(0, total, batch_size)):
        batch = node_ids[i:i + batch_size]

        if organize_by == "year_month":
            batch_items = items[i:i + batch_size]
            for j, nid in enumerate(batch):
                if j < len(batch_items):
                    created = batch_items[j].get("createdDate", "")
                else:
                    created = "unknown"
                date_dir = "unknown"
                if isinstance(created, str) and len(created) >= 7:
                    date_dir = f"{created[:4]}/{created[5:7]}"
                elif created:
                    date_dir = str(created)[:7].replace("-", "/")
                batch_out = out / date_dir
                batch_out.mkdir(parents=True, exist_ok=True)
        else:
            batch_out = out
            batch_out.mkdir(parents=True, exist_ok=True)

        try:
            ap.download(batch, out=str(batch_out))
            downloaded += len(batch)
        except Exception as e:
            failed.extend(batch)
            from amazon_photos_mcp.logging import log_error
            log_error("download_library batch %d/%d failed: %s", batch_idx + 1, num_batches, e)

        # Write progress file
        if progress_path:
            elapsed = time.monotonic() - start_time
            progress_path.write_text(json.dumps({
                "downloaded": downloaded,
                "total": total,
                "percent": round(downloaded / total * 100, 1) if total else 0,
                "current_batch": batch_idx + 1,
                "total_batches": num_batches,
                "elapsed_seconds": round(elapsed, 1),
                "eta_seconds": round(elapsed / (downloaded / total) - elapsed, 1) if downloaded > 0 else None,
                "failed_so_far": len(failed),
            }))

    elapsed = time.monotonic() - start_time

    # Clean up progress file
    if progress_path and progress_path.exists():
        try:
            progress_path.unlink()
        except OSError:
            pass

    return {
        "status": "ok",
        "total_found": total,
        "downloaded": downloaded,
        "failed_count": len(failed),
        "failed_ids": failed[:50],
        "output_dir": str(out),
        "organize_by": organize_by,
        "elapsed_seconds": round(elapsed, 1),
        "import_hint": (
            "For Immich: point External Library at this directory. "
            "For PhotoPrism: use the import folder feature. "
            "For local backup: move/copy this directory to your backup drive."
        ),
    }


# --- Deprecated wrappers ---

@mcp.tool(annotations=_tool_annotations("download_files"))
@_tool
def download_files(node_ids: list[str], output_dir: str = "") -> dict[str, Any]:
    """DEPRECATED: Use download(node_ids=[...]) instead."""
    return download(node_ids=node_ids, output_dir=output_dir)


@mcp.tool(annotations=_tool_annotations("download_by_date"))
@_tool
def download_by_date(
    year: int,
    month: int | None = None,
    day: int | None = None,
    output_dir: str = "",
    media_type: str = "PHOTOS",
    max_items: int = 500,
) -> dict[str, Any]:
    """DEPRECATED: Use download(year=..., month=..., day=...) instead."""
    return download(year=year, month=month, day=day, output_dir=output_dir,
                    media_type=media_type, max_items=max_items)


@mcp.tool(annotations=_tool_annotations("download_for_pipeline"))
@_tool
def download_for_pipeline(
    query: str,
    output_dir: str = "",
    max_items: int = 200,
) -> dict[str, Any]:
    """DEPRECATED: Use download(query=...) instead."""
    return download(query=query, output_dir=output_dir, max_items=max_items)
