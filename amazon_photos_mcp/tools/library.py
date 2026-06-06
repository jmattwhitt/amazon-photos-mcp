"""Library health, integrity, stats, and export tools."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from amazon_photos_mcp import (
    _AMAZON_COOKIE_PATH,
    _get_client,
    _tool,
    _tool_annotations,
    mcp,
)


@mcp.tool(annotations=_tool_annotations("check_db_integrity"))
@_tool
def check_db_integrity() -> dict[str, Any]:
    """Validate the local parquet metadata cache: schema, row count, and file age."""
    import pandas as pd

    EXPECTED_COLUMNS = {"id", "name", "md5", "size", "createdDate", "contentType"}

    db_path = Path(
        os.environ.get(
            "AMAZON_PHOTOS_DB",
            str(_AMAZON_COOKIE_PATH.parent / "ap.parquet"),
        )
    )

    if not db_path.exists():
        return {
            "valid": False,
            "message": f"Parquet DB not found at {db_path}. Call check_connection to initialize.",
            "path": str(db_path),
        }

    age_hours = (time.time() - db_path.stat().st_mtime) / 3600

    try:
        df = pd.read_parquet(db_path)
    except Exception as e:
        return {
            "valid": False,
            "message": f"Parquet DB is unreadable: {e}",
            "path": str(db_path),
            "age_hours": round(age_hours, 1),
        }

    present = set(df.columns)
    missing = EXPECTED_COLUMNS - present

    return {
        "valid": len(missing) == 0,
        "path": str(db_path),
        "row_count": len(df),
        "column_count": len(df.columns),
        "expected_columns_present": list(EXPECTED_COLUMNS & present),
        "missing_columns": list(missing),
        "age_hours": round(age_hours, 1),
        "message": "OK" if not missing else f"Missing expected columns: {missing}",
    }


@mcp.tool(annotations=_tool_annotations("get_library_stats"))
@_tool
def get_library_stats() -> dict[str, Any]:
    """Get a comprehensive health overview of your Amazon Photos library.

    Returns content type breakdown, date range, size distribution,
    duplicate count, storage usage, folder/album/people counts,
    and data quality indicators.
    """
    import pandas as pd

    ap = _get_client()
    db = ap.db
    stats: dict[str, Any] = {}

    if db is None or (hasattr(db, "empty") and db.empty):
        return {"status": "no_data", "message": "Library database is empty. Run check_connection first."}

    # --- Content type breakdown ---
    if "contentType" in db.columns:
        type_counts = db["contentType"].value_counts().to_dict()
        stats["content_types"] = {
            str(k): int(v) for k, v in type_counts.items()
        }
        stats["photo_count"] = sum(
            v for k, v in type_counts.items() if "image" in str(k).lower()
        )
        stats["video_count"] = sum(
            v for k, v in type_counts.items() if "video" in str(k).lower()
        )

    # --- Size stats ---
    if "size" in db.columns:
        sizes = db["size"].dropna()
        if not sizes.empty:
            stats["total_size_bytes"] = int(sizes.sum())
            stats["total_size_gb"] = round(sizes.sum() / (1024 ** 3), 2)
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
    if "createdDate" in db.columns:
        dates = pd.to_datetime(db["createdDate"], errors="coerce").dropna()
        if not dates.empty:
            stats["date_range"] = {
                "oldest": str(dates.min().date()),
                "newest": str(dates.max().date()),
            }
            # Files per year/month histogram
            hist = dates.dt.to_period("M").value_counts().sort_index()
            stats["files_per_month"] = {
                str(k): int(v) for k, v in hist.head(24).items()
            }

    # --- Duplicate count ---
    if "md5" in db.columns:
        md5_counts = db.groupby("md5").size()
        dupe_md5s = md5_counts[md5_counts > 1]
        stats["exact_duplicate_count"] = int(dupe_md5s.sum() - len(dupe_md5s))
        stats["duplicate_groups"] = len(dupe_md5s)

    # --- Folder / album / people counts ---
    try:
        folders = ap.get_folders()
        stats["folder_count"] = len(folders) if hasattr(folders, "__len__") else "unavailable"
    except Exception:
        stats["folder_count"] = "unavailable"

    try:
        albums = ap.albums()
        stats["album_count"] = len(albums) if hasattr(albums, "__len__") else "unavailable"
    except Exception:
        stats["album_count"] = "unavailable"

    try:
        people = ap.aggregations("allPeople", out="")
        stats["people_count"] = len(people) if isinstance(people, list) else "unavailable"
    except Exception:
        stats["people_count"] = "unavailable"

    # --- Data quality ---
    quality: dict[str, int] = {}
    if "createdDate" in db.columns:
        quality["missing_dates"] = int(db["createdDate"].isna().sum())
    if "location.latitude" in db.columns:
        quality["missing_location"] = int(db["location.latitude"].isna().sum())
    stats["data_quality"] = quality

    # --- Storage usage vs quota ---
    try:
        usage = ap.usage()
        if hasattr(usage, "json"):
            u = usage.json()
            stats["storage_used_gb"] = round(u.get("used", 0) / (1024 ** 3), 2)
            stats["storage_quota_gb"] = round(u.get("available", 0) / (1024 ** 3), 2)
            used_pct = (u.get("used", 0) / max(u.get("available", 1), 1)) * 100
            stats["storage_used_percent"] = round(used_pct, 1)
    except Exception:
        pass

    stats["total_items"] = len(db)
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
    from amazon_photos_mcp import SLIM_FIELDS, _clean_row

    ap = _get_client()
    db = ap.db

    if db is None or (hasattr(db, "empty") and db.empty):
        return {"status": "no_data", "message": "Database is empty. Run check_connection first."}

    # Apply filter if provided
    if filter_query:
        df = ap.query(filter_query)
        if df is None or (hasattr(df, "empty") and df.empty):
            return {"status": "no_results", "query": filter_query, "message": "Query returned no results."}
    else:
        df = db.copy()

    if not output_path:
        ext = "csv" if fmt == "csv" else "json"
        output_path = str(Path.home() / "Downloads" / f"amazon-photos-export.{ext}")

    # Clean and optionally slim
    records = [_clean_row(r) for r in df.to_dict(orient="records")]
    if slim:
        records = [{k: v for k, v in r.items() if k in SLIM_FIELDS} for r in records]
    if not include_exif:
        records = [
            {k: v for k, v in r.items() if not k.startswith(("image.", "camera", "exif", "gps"))}
            for r in records
        ]

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "csv":
        import pandas as pd
        pd.DataFrame(records).to_csv(out, index=False)
    else:
        # JSON: organize by year/month for Immich compatibility
        if "createdDate" in df.columns:
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
        "file_size_mb": round(file_size / (1024 ** 2), 2),
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
    import pandas as pd

    ap = _get_client()
    db = ap.db

    if db is None or (hasattr(db, "empty") and db.empty):
        return {"status": "no_data", "message": "Database is empty. Run check_connection first."}

    if "createdDate" not in db.columns:
        return {"status": "no_data", "message": "createdDate column not found in database."}

    dates = pd.to_datetime(db["createdDate"], errors="coerce").dropna()
    if dates.empty:
        return {"status": "no_data", "message": "No valid dates found in database."}

    monthly = dates.dt.to_period("M").value_counts().sort_index()

    # Find all months between oldest and newest
    full_range = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
    full_counts = monthly.reindex(full_range, fill_value=0)

    gaps = [
        {
            "month": str(month),
            "photo_count": int(full_counts[month]),
            "gap_size": "empty" if full_counts[month] == 0 else "low",
        }
        for month in full_range
        if full_counts[month] < min_photos_per_month
    ]
    gaps.sort(key=lambda g: g["photo_count"])

    gap_months = [g for g in gaps if g["gap_size"] == "empty"]
    low_months = [g for g in gaps if g["gap_size"] == "low"]

    return {
        "date_range": {
            "oldest": str(monthly.index.min()),
            "newest": str(monthly.index.max()),
        },
        "months_scanned": len(full_range),
        "total_photos": int(dates.count()),
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
