"""Duplicate detection and cleanup tools."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from amazon_photos_mcp.client import _get_client
from amazon_photos_mcp.decorators import _tool
from amazon_photos_mcp.server import _tool_annotations, mcp
from amazon_photos_mcp.utils import _clean_row, _is_nan


@mcp.tool(annotations=_tool_annotations("find_duplicates"))
@_tool
def find_duplicates(max_groups: int = 50, refresh_db: bool = False) -> dict[str, Any]:
    """Find exact duplicate files in your library by MD5 hash. Read-only."""
    ap = _get_client()
    items = ap.query("type:(PHOTOS OR VIDEOS)")
    if not items:
        return {"error": True, "code": "NO_DATA", "message": "Library is empty."}
    import pandas as pd

    db = pd.json_normalize(items)

    if "md5" not in db.columns:
        return {
            "error": True,
            "code": "SCHEMA_ERROR",
            "message": "md5 column missing. Call check_connection to rebuild.",
        }

    md5_counts = db.groupby("md5").size()
    dupe_md5s = md5_counts[md5_counts > 1]

    if dupe_md5s.empty:
        return {"total_duplicate_files": 0, "removable_copies": 0, "groups": []}

    total_files = int(dupe_md5s.sum())
    removable = int(total_files - len(dupe_md5s))
    dupe_rows = db[db["md5"].isin(dupe_md5s.index)].copy()

    groups: list[dict[str, Any]] = []
    for md5_hash, group_df in dupe_rows.groupby("md5"):
        if len(groups) >= max_groups:
            break
        files: list[dict[str, Any]] = []
        for _, row in group_df.iterrows():
            files.append(
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "folder": row.get("parentMap.FOLDER") if not _is_nan(row.get("parentMap.FOLDER")) else None,
                    "createdDate": str(row.get("createdDate")) if not _is_nan(row.get("createdDate")) else None,
                    "size": int(row["size"]) if not _is_nan(row.get("size")) else None,
                }
            )
        files.sort(key=lambda f: f["createdDate"] or "")
        groups.append({"md5": str(md5_hash), "count": len(files), "files": files})

    groups.sort(key=lambda g: g["count"], reverse=True)

    return {
        "total_duplicate_files": total_files,
        "removable_copies": removable,
        "total_groups": len(dupe_md5s),
        "groups_shown": len(groups),
        "groups": groups,
    }


@mcp.tool(annotations=_tool_annotations("preview_duplicate_group"))
@_tool
def preview_duplicate_group(md5_hash: str) -> dict[str, Any]:
    """Show all copies of an MD5 hash with full metadata, oldest first."""
    ap = _get_client()
    items = ap.query("type:(PHOTOS OR VIDEOS)")
    if not items:
        return {"error": True, "code": "NO_DATA", "message": "Library is empty."}
    import pandas as pd

    db = pd.json_normalize(items)

    if "md5" not in db.columns:
        return {"error": True, "code": "SCHEMA_ERROR", "message": "md5 column not found in database."}

    group = db[db["md5"] == md5_hash]
    if group.empty:
        return {"error": True, "code": "NOT_FOUND", "message": f"No files found with md5={md5_hash}"}

    records = [_clean_row(r) for r in group.to_dict(orient="records")]
    records.sort(key=lambda r: str(r.get("createdDate") or ""))
    return {
        "md5": md5_hash,
        "count": len(records),
        "recommended_keep": records[0].get("id") if records else None,
        "files": records,
    }


@mcp.tool(annotations=_tool_annotations("find_near_duplicates"))
@_tool
def find_near_duplicates(
    threshold: int = 5,
    max_groups: int = 50,
    sample_size: int = 200,
) -> dict[str, Any]:
    """Find visually similar (near-duplicate) photos using perceptual hashing.

    Downloads a sample of photos, computes pHash, and groups near-duplicates.
    Complements find_duplicates (MD5 exact match). Use this after exact dedup
    to find resized, re-encoded, or slightly edited copies.

    Args:
        threshold: Hamming distance threshold (0-64). Lower = stricter. Default 5.
                   A difference of 1-2 = nearly identical, 5-10 = similar, >10 = different.
        max_groups: Maximum groups to return
        sample_size: Maximum photos to analyze (downloads them temporarily)
    """
    from amazon_photos_mcp.phash import compute_phash
    from amazon_photos_mcp.phash import find_near_duplicates as _find_near

    ap = _get_client()
    items = ap.query("type:(PHOTOS OR VIDEOS)")
    if not items:
        return {"error": True, "code": "NO_DATA", "message": "Library is empty."}
    import pandas as pd

    db = pd.json_normalize(items)

    if db is None or (hasattr(db, "empty") and db.empty):
        return {"status": "no_data", "message": "Database is empty. Run search_photos or check_connection first."}

    if "contentType" in db.columns:
        photos = db[db["contentType"].str.contains("image", na=False)].head(sample_size)
    else:
        photos = db.head(sample_size)

    if photos.empty:
        return {"status": "no_photos", "message": "No photos found in database."}

    file_hashes: dict[str, str] = {}
    # Map downloaded filenames back to node IDs for accurate group results
    name_to_id: dict[str, str] = {}
    for _, row in photos.iterrows():
        name = str(row.get("name", row.get("id", "")))
        node_id = str(row["id"])
        name_to_id.setdefault(name, node_id)
        stem = Path(name).stem
        name_to_id.setdefault(stem, node_id)

    temp_dir = Path(tempfile.mkdtemp(prefix="ap-phash-"))

    try:
        photo_ids = photos["id"].tolist()
        ap.download(photo_ids, out=str(temp_dir))

        for f in temp_dir.iterdir():
            if f.is_file():
                phash = compute_phash(f)
                if phash:
                    node_id = name_to_id.get(f.name) or name_to_id.get(f.stem) or f.stem
                    file_hashes[node_id] = phash
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if not file_hashes:
        return {"status": "no_hashes", "message": "Could not compute hashes for any sample photos."}

    groups = _find_near(file_hashes, threshold=threshold)
    groups = sorted(groups, key=lambda g: g["count"], reverse=True)[:max_groups]

    return {
        "sample_size": len(photos),
        "photos_hashed": len(file_hashes),
        "threshold": threshold,
        "groups_found": len(groups),
        "groups": groups,
    }


@mcp.tool(annotations=_tool_annotations("keep_specific"))
@_tool
def keep_specific(keep_id: str, md5_hash: str, dry_run: bool = True) -> dict[str, Any]:
    """Keep a specific copy and trash all other duplicates in an MD5 group."""
    ap = _get_client()
    items = ap.query("type:(PHOTOS OR VIDEOS)")
    if not items:
        return {"error": True, "code": "NO_DATA", "message": "Library is empty."}
    import pandas as pd

    db = pd.json_normalize(items)

    if "md5" not in db.columns:
        return {"error": True, "code": "SCHEMA_ERROR", "message": "md5 column not found in database."}

    group = db[db["md5"] == md5_hash]
    if group.empty:
        return {"error": True, "code": "NOT_FOUND", "message": f"No files found with md5={md5_hash}"}

    trash_ids = [row.get("id") for _, row in group.iterrows() if row.get("id") and row.get("id") != keep_id]

    if not trash_ids:
        return {"status": "nothing_to_do", "message": "Only one copy found or keep_id is not in this group."}

    if dry_run:
        return {
            "action": "dry_run",
            "keep_id": keep_id,
            "trash_ids": trash_ids,
            "message": f"Would trash {len(trash_ids)} copy/copies. Set dry_run=False to execute.",
        }

    ap.trash(trash_ids)
    return {
        "status": "ok",
        "action": "trashed",
        "kept": keep_id,
        "node_ids": trash_ids,
        "count": len(trash_ids),
        "message": f"Trashed {len(trash_ids)} duplicate copy/copies. Recoverable from trash for 30 days.",
    }


@mcp.tool(annotations=_tool_annotations("trash_duplicates"))
@_tool
def trash_duplicates(
    md5_hashes: list[str] | None = None,
    dry_run: bool = True,
    refresh_db: bool = False,
) -> dict[str, Any]:
    """Trash duplicate copies, keeping the oldest of each MD5 group."""
    ap = _get_client()
    items = ap.query("type:(PHOTOS OR VIDEOS)")
    if not items:
        return {"error": True, "code": "NO_DATA", "message": "Library is empty."}
    import pandas as pd

    db = pd.json_normalize(items)

    if "md5" not in db.columns:
        return {"error": True, "code": "SCHEMA_ERROR", "message": "md5 column not found in database."}

    md5_counts = db.groupby("md5").size()
    dupe_md5s = set(md5_counts[md5_counts > 1].index)

    if md5_hashes is not None:
        dupe_md5s = dupe_md5s & set(md5_hashes)

    if not dupe_md5s:
        return {
            "action": "dry_run" if dry_run else "trashed",
            "groups_processed": 0,
            "files_trashed": 0,
            "files_kept": 0,
            "node_ids": [],
            "message": "No duplicates found to process.",
        }

    dupe_rows = db[db["md5"].isin(dupe_md5s)].copy()
    trash_ids: list[str] = []
    keep_ids: list[str] = []

    for _, group_df in dupe_rows.groupby("md5"):
        # Sort NaN-dated items first so they get trashed, not kept.
        # Items with unknown creation dates should not be auto-kept.
        sorted_group = group_df.sort_values("createdDate", ascending=True, na_position="first")
        keep_ids.append(sorted_group.iloc[0].get("id"))
        for _, row in sorted_group.iloc[1:].iterrows():
            rid = row.get("id")
            if rid:
                trash_ids.append(rid)

    result: dict[str, Any] = {
        "action": "dry_run" if dry_run else "trashed",
        "groups_processed": len(dupe_md5s),
        "files_kept": len(keep_ids),
        "files_trashed": len(trash_ids),
        "node_ids": trash_ids,
    }

    if dry_run:
        result["message"] = (
            f"Would trash {len(trash_ids)} duplicate copies across {len(dupe_md5s)} groups. "
            "Set dry_run=False to execute."
        )
        sample = db[db["id"].isin(trash_ids[:10])]
        result["sample_trashed"] = [
            {"id": r["id"], "name": r.get("name"), "md5": r.get("md5")} for _, r in sample.iterrows()
        ]
    else:
        batch_size = 100
        for i in range(0, len(trash_ids), batch_size):
            ap.trash(trash_ids[i : i + batch_size])
        result["message"] = f"Trashed {len(trash_ids)} duplicate copies. Items are recoverable from trash for 30 days."

    return result


@mcp.tool(annotations=_tool_annotations("trash_near_duplicates"))
@_tool
def trash_near_duplicates(
    group: list[str],
    dry_run: bool = True,
    keep_strategy: str = "best_quality",
) -> dict[str, Any]:
    """Trash near-duplicate photos, keeping the best quality item from a group.

    Use after find_near_duplicates to clean up visually similar copies.

    Args:
        group: List of node IDs in a near-duplicate group (from find_near_duplicates)
        dry_run: If True, preview what would be trashed without executing
        keep_strategy: How to choose which photo to keep:
            "best_quality" (default) - prefers JPEG over HEIC, larger file, higher resolution
            "oldest" - keeps the oldest
            "newest" - keeps the newest
    """
    ap = _get_client()
    items = ap.query("type:(PHOTOS OR VIDEOS)")
    if not items:
        return {"error": True, "code": "NO_DATA", "message": "Library is empty."}
    import pandas as pd

    db = pd.json_normalize(items)

    if len(group) <= 1:
        return {"status": "nothing_to_do", "message": "Group has only 0-1 items; nothing to trash."}

    # Find group items in DB
    group_rows = db[db["id"].isin(group)]
    if group_rows.empty:
        return {"status": "error", "message": "None of the provided node IDs were found in the database."}

    items = group_rows.to_dict(orient="records")
    items = [_clean_row(r) for r in items]

    if keep_strategy == "oldest":
        items.sort(key=lambda r: str(r.get("createdDate") or ""))
        keep = items[0]
    elif keep_strategy == "newest":
        items.sort(key=lambda r: str(r.get("createdDate") or ""), reverse=True)
        keep = items[0]
    else:
        # best_quality: prefer JPEG > HEIC > other, larger file, higher resolution
        def _quality_score(item: dict[str, Any]) -> tuple[int, int, int]:
            ct = str(item.get("contentType", "")).lower()
            type_score = 3 if "jpeg" in ct else (2 if "heic" in ct or "heif" in ct else 1)
            size = int(item.get("size", 0) or 0)
            w = int(item.get("image.width", 0) or 0)
            h = int(item.get("image.height", 0) or 0)
            return (type_score, size, w * h)

        items.sort(key=_quality_score, reverse=True)
        keep = items[0]

    trash_ids: list[str] = []
    for r in items:
        rid = r.get("id")
        if isinstance(rid, str) and rid != keep.get("id"):
            trash_ids.append(rid)

    result: dict[str, Any] = {
        "action": "dry_run" if dry_run else "trashed",
        "group_size": len(items),
        "keep_id": keep.get("id"),
        "keep_name": keep.get("name"),
        "keep_strategy": keep_strategy,
        "keep_score": {
            "contentType": keep.get("contentType"),
            "size": keep.get("size"),
            "resolution": f"{keep.get('image.width', '?')}x{keep.get('image.height', '?')}",
        },
        "trash_ids": trash_ids,
    }

    if dry_run:
        result["message"] = (
            f"Would keep '{keep.get('name')}' and trash {len(trash_ids)} near-duplicate(s). "
            "Set dry_run=False to execute."
        )
    else:
        batch_size = 50
        for i in range(0, len(trash_ids), batch_size):
            ap.trash(trash_ids[i : i + batch_size])
        result["message"] = (
            f"Kept '{keep.get('name')}' and trashed {len(trash_ids)} near-duplicate(s). "
            "Recoverable from trash for 30 days."
        )

    return result
