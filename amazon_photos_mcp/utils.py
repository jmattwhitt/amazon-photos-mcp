"""Utility functions for Amazon Photos MCP."""

import os
from pathlib import Path
from typing import Any


PIPELINE_DEFAULT_DIR = os.environ.get(
    "AMAZON_PHOTOS_PIPELINE_DIR",
    str(Path.home() / "Downloads" / "amazon-photos-pipeline"),
)

SLIM_FIELDS = {
    "id",
    "name",
    "createdDate",
    "modifiedDate",
    "contentType",
    "size",
    "md5",
    "settings.favorite",
    "settings.hidden",
    "image.width",
    "image.height",
    "location.latitude",
    "location.longitude",
}


def _is_nan(v: Any) -> bool:
    if v is None:
        return True
    try:
        if isinstance(v, float) and v != v:
            return True
    except (TypeError, ValueError):
        pass
    return False


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (None if _is_nan(v) else v) for k, v in row.items()}


def _safe_df_to_list(df: Any, max_results: int = 50, slim: bool = False) -> list[dict[str, Any]]:
    """Convert DataFrame to list of dicts with truncation and dedup.

    Note: duplicate IDs are silently dropped via drop_duplicates.
    Callers that need exact counts should check before/after lengths.
    """
    if df is None:
        return []
    if isinstance(df, list):
        return df[:max_results]
    if hasattr(df, "empty") and df.empty:
        return []
    if hasattr(df, "columns") and "id" in df.columns:
        df = df.drop_duplicates(subset=["id"])
    if not hasattr(df, "to_dict"):
        return [{"value": str(df)}]
    records = df.head(max_results).to_dict(orient="records")
    result = [_clean_row(r) for r in records]
    if slim:
        result = [{k: v for k, v in r.items() if k in SLIM_FIELDS} for r in result]
    return result


def _safe_df_to_result(df: Any, max_results: int = 50, slim: bool = False) -> dict[str, Any]:
    """Like _safe_df_to_list but returns dict with truncation metadata."""
    if df is None:
        return {"items": [], "has_more": False, "total": 0}
    if isinstance(df, list):
        total = len(df)
        items = df[:max_results]
        return {"items": items, "has_more": total > max_results, "total": total}
    if hasattr(df, "empty") and df.empty:
        return {"items": [], "has_more": False, "total": 0}
    if hasattr(df, "columns") and "id" in df.columns:
        df = df.drop_duplicates(subset=["id"])
    total = len(df)
    if not hasattr(df, "to_dict"):
        return {"items": [{"value": str(df)}], "has_more": False, "total": 1}
    items = df.head(max_results).to_dict(orient="records")
    items = [_clean_row(r) for r in items]
    if slim:
        items = [{k: v for k, v in r.items() if k in SLIM_FIELDS} for r in items]
    return {"items": items, "has_more": total > max_results, "total": total}
