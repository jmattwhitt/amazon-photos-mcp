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


def _get_items(ap: Any) -> list[dict] | None:
    """Fetch all items and return a list, or None if empty."""
    items = ap.query("type:(PHOTOS OR VIDEOS)")
    return items if items else None


@mcp.tool(annotations=_tool_annotations("find_duplicates"))
@_tool
def find_duplicates(max_groups: int = 50) -> dict[str, Any]:
    """Find exact duplicate files in your library by MD5 hash. Read-only."""
    ap = _get_client()
    items = _get_items(ap)
    if not items:
        return {"error": True, "code": "NO_DATA", "message": "Library is empty."}

        md5_groups: dict[str, list[dict]] = {}
    for item in items:
        md5 = item.get("md5")
        if md5:
            md5_groups.setdefault(str(md5), []).append(item)
    dupe_md5s = {md5 for md5, grp in md5_groups.items() if len(grp) > 1}

    if not dupe_md5s:
        return {"total_duplicate_files": 0, "removable_copies": 0, "groups": []}

    total_files = sum(len(md5_groups[md5]) for md5 in dupe_md5s)
    removable = total_files - len(dupe_md5s)

    groups: list[dict[str, Any]] = []
    for md5_hash in sorted(dupe_md5s):
        if len(groups) >= max_groups:
            break
        files = []
        for item in md5_groups[md5_hash]:
            files.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "folder": item.get("parentMap", {}).get("FOLDER"),
                "createdDate": str(item["createdDate"]) if item.get("createdDate") else None,
                "size": int(item["size"]) if item.get("size") is not None else None,
            })
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
    items = _get_items(ap)
    if not items:
        return {"error": True, "code": "NO_DATA", "message": "Library is empty."}

    group = [item for item in items if item.get("md5") == md5_hash]
    if not group:
        return {"error": True, "code": "NOT_FOUND", "message": f"No files found with md5={md5_hash}"}

    records = [_clean_row(r) for r in group]
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
    items = _get_items(ap)
    if not items:
        return {"status": "no_data", "message": "Library is empty."}

    if not items:
        return {"status": "no_data", "message": "Database is empty. Run search_photos or check_connection first."}

    photos = [item for item in items if "image" in str(item.get("contentType", "")).lower()][:sample_size]
    if not photos:
        return {"status": "no_photos", "message": "No photos found in database."}

    file_hashes: dict[str, str] = {}
    # Map downloaded filenames back to node IDs for accurate group results
    name_to_id: dict[str, str] = {}
    for item in photos:
        name = str(item.get("name", item.get("id", "")))
        node_id = str(item["id"])
        name_to_id.setdefault(name, node_id)
        stem = Path(name).stem
        name_to_id.setdefault(stem, node_id)

    temp_dir = Path(tempfile.mkdtemp(prefix="ap-phash-"))

    try:
        photo_ids = [item["id"] for item in photos]
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
    items = _get_items(ap)
    if not items:
        return {"error": True, "code": "NO_DATA", "message": "Library is empty."}

    group = [item for item in items if item.get("md5") == md5_hash]
    if not group:
        return {"error": True, "code": "NOT_FOUND", "message": f"No files found with md5={md5_hash}"}

    trash_ids = [item.get("id") for item in group if item.get("id") and item.get("id") != keep_id]

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
) -> dict[str, Any]:
    """Trash duplicate copies, keeping the oldest of each MD5 group."""
    ap = _get_client()
    items = _get_items(ap)
    if not items:
        return {"error": True, "code": "NO_DATA", "message": "Library is empty."}

        md5_groups_dup: dict[str, list[dict]] = {}
    for item in items:
        md5 = item.get("md5")
        if md5:
            md5_groups_dup.setdefault(str(md5), []).append(item)
    dupe_md5s = {md5 for md5, grp in md5_groups_dup.items() if len(grp) > 1}

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

    trash_ids: list[str] = []
    keep_ids: list[str] = []

    for md5_hash in sorted(dupe_md5s):
        group = md5_groups_dup[md5_hash]
        group.sort(key=lambda i: str(i.get("createdDate") or ""))
        keep_ids.append(group[0].get("id"))
        for item in group[1:]:
            rid = item.get("id")
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
        result["sample_trashed"] = [
            {"id": item["id"], "name": item.get("name"), "md5": item.get("md5")}
            for item in items if item.get("id") in trash_ids[:10]
        ]
    else:
        ap.trash(trash_ids)
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
    items = _get_items(ap)
    if not items:
        return {"error": True, "code": "NO_DATA", "message": "Library is empty."}

    if len(group) <= 1:
        return {"status": "nothing_to_do", "message": "Group has only 0-1 items; nothing to trash."}

    # Find group items in DB
    group_rows = [item for item in items if item.get("id") in group]
    if not group_rows:
        return {"status": "error", "message": "None of the provided node IDs were found in the database."}

    items = [_clean_row(r) for r in group_rows]

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
            w = int(item.get("image", {}).get("width", 0) or 0)
            h = int(item.get("image", {}).get("height", 0) or 0)
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
            "resolution": f"{keep.get('image', {}).get('width', '?')}x{keep.get('image', {}).get('height', '?')}",
        },
        "trash_ids": trash_ids,
    }

    if dry_run:
        result["message"] = (
            f"Would keep '{keep.get('name')}' and trash {len(trash_ids)} near-duplicate(s). "
            "Set dry_run=False to execute."
        )
    else:
        ap.trash(trash_ids)
        result["message"] = (
            f"Kept '{keep.get('name')}' and trashed {len(trash_ids)} near-duplicate(s). "
            "Recoverable from trash for 30 days."
        )

    return result
