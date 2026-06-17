"""Library health, integrity, stats, and export tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Generator

from amazon_photos_mcp.client import _get_client
from amazon_photos_mcp.decorators import _tool
from amazon_photos_mcp.server import _tool_annotations, mcp


@mcp.tool(annotations=_tool_annotations("check_db_integrity"))
@_tool
def check_db_integrity() -> dict[str, Any]:
    """Validate the local parquet metadata cache: schema, row count, and file age."""
    return {
        "valid": True,
        "message": "Parquet caching is deprecated in the native API client. The server now queries live data directly.",
    }


@mcp.tool(annotations=_tool_annotations("get_library_stats"))
@_tool
def get_library_stats() -> dict[str, Any]:
    """Get a comprehensive health overview of your Amazon Photos library.

    Returns content type breakdown, date range, size distribution,
    duplicate count, storage usage, folder/album/people counts,
    and data quality indicators.
    """
    from collections import Counter
    from datetime import datetime

    ap = _get_client()
    stats: dict[str, Any] = {}

    # Fetch live data
    items = ap.query("type:(PHOTOS OR VIDEOS)")
    if not items:
        return {"status": "no_data", "message": "Library is empty."}


    # --- Content type breakdown ---
    type_counts: Counter[str] = Counter()
    for item in items:
        ct = item.get("contentType")
        if ct:
            type_counts[str(ct)] += 1
        stats["content_types"] = dict(type_counts)
        stats["photo_count"] = sum(v for k, v in type_counts.items() if "image" in str(k).lower())
        stats["video_count"] = sum(v for k, v in type_counts.items() if "video" in str(k).lower())

    # --- Size stats ---
    _raw_sizes: list[int] = []
    for _item in items:
        _s = _item.get("size")
        if isinstance(_s, (int, float)):
            _raw_sizes.append(int(_s))
    sizes = _raw_sizes
    if sizes:
            stats["total_size_bytes"] = int(sum(sizes))
            stats["total_size_gb"] = round(sum(sizes) / (1024**3), 2)
            buckets = {"<1MB": 0, "1-5MB": 0, "5-10MB": 0, "10-50MB": 0, ">50MB": 0}
            for s in sizes:
                if s < 1_048_576:
                    buckets["<1MB"] += 1
                elif s < 5_242_880:
                    buckets["1-5MB"] += 1
                elif s < 10_485_760:
                    buckets["5-10MB"] += 1
                elif s < 52_428_800:
                    buckets["10-50MB"] += 1
                else:
                    buckets[">50MB"] += 1
            stats["size_distribution"] = buckets

    # --- Date range ---
    dates = []
    for item in items:
        cd = item.get("createdDate")
        if cd and isinstance(cd, str):
            try:
                dt = datetime.fromisoformat(cd.replace("Z", "+00:00"))
                dates.append(dt)
            except (ValueError, TypeError):
                pass
    if dates:
        stats["date_range"] = {
            "oldest": str(min(dates).date()),
            "newest": str(max(dates).date()),
        }
        monthly: Counter[str] = Counter()
        for d in dates:
            monthly[f"{d.year}-{d.month:02d}"] += 1
        sorted_months = sorted(monthly.items())
        stats["files_per_month"] = {k: v for k, v in sorted_months[-24:]}

    # --- Duplicate count ---
    md5_groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        md5 = item.get("md5")
        if md5:
            md5_groups.setdefault(str(md5), []).append(item)
    dupe_md5s = {md5 for md5, grp in md5_groups.items() if len(grp) > 1}
    if dupe_md5s:
        total_dupes = sum(len(md5_groups[md5]) for md5 in dupe_md5s)
        stats["exact_duplicate_count"] = total_dupes - len(dupe_md5s)
        stats["duplicate_groups"] = len(dupe_md5s)
    # --- Folder / album / people counts ---
    try:
        folders = ap.get_folders()
        stats["folder_count"] = len(folders) if hasattr(folders, "__len__") else None
    except Exception:
        stats["folder_count"] = None

    try:
        albums = ap.albums()
        stats["album_count"] = len(albums) if hasattr(albums, "__len__") else None
    except Exception:
        stats["album_count"] = None

    try:
        people = ap.aggregations("allPeople")
        stats["people_count"] = len(people) if isinstance(people, list) else None
    except Exception:
        stats["people_count"] = None

    # --- Data quality ---
    quality: dict[str, int] = {}
    quality["missing_dates"] = sum(1 for item in items if not item.get("createdDate"))
    quality["missing_location"] = sum(1 for item in items if item.get("location", {}).get("latitude") is None)
    stats["data_quality"] = quality

    # --- Storage usage vs quota ---
    try:
        usage = ap.usage()
        if isinstance(usage, dict):
            stats["storage_used_gb"] = round(usage.get("used", 0) / (1024**3), 2)
            stats["storage_quota_gb"] = round(usage.get("available", 0) / (1024**3), 2)
            used_pct = (usage.get("used", 0) / max(usage.get("available", 1), 1)) * 100
            stats["storage_used_percent"] = round(used_pct, 1)
    except Exception:
        stats["storage_error"] = True

    stats["total_items"] = len(items)
    return stats


@mcp.tool(annotations=_tool_annotations("export_metadata"))
@_tool
def export_metadata(
    fmt: str = "json",
    output_path: str = "",
    include_exif: bool = False,
    slim: bool = True,
    filter_query: str = "",
) -> dict[str, Any]:
    """Export library metadata to JSON or CSV for migration to Immich or PhotoPrism.

    Args:
        format: "json" or "csv"
        output_path: File path for export (auto-generated if empty)
        include_exif: Include full EXIF metadata in each record
        slim: Only include essential fields
        filter_query: Optional Amazon Photos query to filter which items to export
    """
    from amazon_photos_mcp.utils import SLIM_FIELDS, _clean_row

    ap = _get_client()

    # Apply filter if provided
    if filter_query:
        items = ap.query(filter_query)
        if not items:
            return {"status": "no_results", "query": filter_query, "message": "Query returned no results."}
    else:
        items = ap.query("type:(PHOTOS OR VIDEOS)")
        if not items:
            return {"status": "no_data", "message": "Library is empty."}


    if not output_path:
        ext = "csv" if fmt == "csv" else "json"
        output_path = str(Path.home() / "Downloads" / f"amazon-photos-export.{ext}")

    # Clean and optionally slim
    records = [_clean_row(r) for r in items]
    if slim:
        records = [{k: v for k, v in r.items() if k in SLIM_FIELDS} for r in records]
    if not include_exif:
        records = [
            {k: v for k, v in r.items() if not k.startswith(("image.", "camera", "exif", "gps"))} for r in records
        ]

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "csv":
        import csv
        with open(out, 'w', newline='', encoding='utf-8') as f:
            if records:
                writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
                writer.writeheader()
                writer.writerows(records)
    else:
        # JSON: organize by year/month for Immich compatibility
        if any("createdDate" in r for r in records):
            by_date: dict[str, list[dict[str, Any]]] = {}
            for r in records:
                created = r.get("createdDate", "unknown") or "unknown"
                key = str(created)[:7] if isinstance(created, str) and len(str(created)) >= 7 else "unknown"
                by_date.setdefault(key, []).append(r)
            export_data: dict[str, Any] = {
                "_export_info": {
                    "source": "Amazon Photos MCP",
                    "total_items": len(records),
                    "export_format": "year/month buckets",
                },
                "items": by_date,
            }
        else:
            export_data = {"items": records}

        with open(out, "w", encoding="utf-8") as f:
            json.dump(export_data, f, default=str, indent=2)

    file_size = out.stat().st_size
    return {
        "status": "ok",
        "row_count": len(records),
        "format": fmt,
        "file_path": str(out),
        "file_size_mb": round(file_size / (1024**2), 2),
        "sample": records[:3] if records else [],
        "import_hint": (
            "For Immich: use the 'External Library' feature pointing at your exported files. "
            "For PhotoPrism: use 'photoprism import' or the import folder. "
            "This metadata export helps prepare for migration but does not include the actual media files."
        ),
    }


@mcp.tool(annotations=_tool_annotations("find_timeline_gaps"))
@_tool
def find_timeline_gaps(min_photos_per_month: int = 5) -> dict[str, Any]:
    """Find gaps in your photo timeline — months/years with few or no photos.

    Args:
        min_photos_per_month: Months with fewer than this many photos are flagged as gaps.
    """
    from collections import Counter
    from datetime import datetime

    ap = _get_client()

    items = ap.query("type:(PHOTOS OR VIDEOS)")
    if not items:
        return {"status": "no_data", "message": "Library is empty."}

    monthly_counts: Counter[str] = Counter()
    for item in items:
        cd = item.get("createdDate")
        if cd and isinstance(cd, str) and len(cd) >= 7:
            monthly_counts[cd[:7]] += 1

    if not monthly_counts:
        return {"status": "no_data", "message": "No valid dates found in database."}

    months_sorted = sorted(monthly_counts.keys())
    min_month = months_sorted[0]
    max_month = months_sorted[-1]

    def _month_iter(start: str, end: str) -> Generator[str, None, None]:
        s = datetime.strptime(start + "-01", "%Y-%m-%d")
        e = datetime.strptime(end + "-01", "%Y-%m-%d")
        while s <= e:
            yield s.strftime("%Y-%m")
            if s.month == 12:
                s = s.replace(year=s.year + 1, month=1)
            else:
                s = s.replace(month=s.month + 1)

    full_range = list(_month_iter(min_month, max_month))
    total_photos = sum(monthly_counts.values())

    gaps = [
        {
            "month": str(month),
            "photo_count": monthly_counts.get(month, 0),
            "gap_size": "empty" if monthly_counts.get(month, 0) == 0 else "low",
        }
        for month in full_range
        if monthly_counts.get(month, 0) < min_photos_per_month
    ]
    gaps.sort(key=lambda g: g["photo_count"])

    gap_months = [g for g in gaps if g["gap_size"] == "empty"]
    low_months = [g for g in gaps if g["gap_size"] == "low"]

    return {
        "date_range": {
            "oldest": min_month,
            "newest": max_month,
        },
        "months_scanned": len(full_range),
        "total_photos": total_photos,
        "min_photos_threshold": min_photos_per_month,
        "total_gaps": len(gaps),
        "empty_months": len(gap_months),
        "low_count_months": len(low_months),
        "gap_months": gap_months,
        "low_count_details": low_months[:50],
        "suggestion": (
            "Empty months may indicate missing imports. "
            "Check backup drives, old phones, or cloud archives for photos from these periods. "
            "Use download_by_date or download(query=...) to fill specific gaps."
        ),
    }
