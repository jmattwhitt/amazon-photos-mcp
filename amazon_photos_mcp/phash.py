"""Perceptual hash support for near-duplicate photo detection.

Uses pHash (DCT-based) with configurable Hamming distance threshold.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def compute_phash(file_path: str | Path) -> str | None:
    """Compute perceptual hash of an image file.

    Returns a hex string or None if the file can't be opened as an image.
    """
    try:
        import imagehash
        from PIL import Image

        img = Image.open(str(file_path))
        phash = imagehash.phash(img)
        return str(phash)
    except Exception:
        return None


def hamming_distance(h1: str, h2: str) -> int:
    """Compute Hamming distance between two hex hash strings."""
    if len(h1) != len(h2):
        return max(len(h1), len(h2)) * 4
    try:
        n1 = int(h1, 16)
        n2 = int(h2, 16)
        return (n1 ^ n2).bit_count()
    except ValueError:
        return 999


def find_near_duplicates(
    file_hashes: dict[str, str],
    threshold: int = 5,
) -> list[dict[str, Any]]:
    """Group files whose perceptual hashes are within threshold Hamming distance.

    Returns list of groups, each with: node_ids, count, phash_sample, distances
    """
    ids = list(file_hashes.keys())
    seen: set[str] = set()
    groups: list[dict[str, Any]] = []

    for i, id_i in enumerate(ids):
        if id_i in seen:
            continue
        h1 = file_hashes[id_i]
        group: list[str] = [id_i]
        group_hashes: list[str] = [h1]
        for j in range(i + 1, len(ids)):
            id_j = ids[j]
            if id_j in seen:
                continue
            h2 = file_hashes[id_j]
            if hamming_distance(h1, h2) <= threshold:
                group.append(id_j)
                group_hashes.append(h2)
                seen.add(id_j)
        if len(group) > 1:
            seen.add(id_i)
            groups.append(
                {
                    "node_ids": group,
                    "count": len(group),
                    "phash_sample": h1,
                    "distances": [hamming_distance(h1, h) for h in group_hashes],
                }
            )

    return groups
