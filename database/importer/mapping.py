"""Import result mapping for operator follow-up.

Only company source IDs and app-generated database IDs are emitted. Profile names,
messages, and other imported content are intentionally excluded.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from pathlib import Path


def render_id_mapping(
    source_system: str,
    users: Mapping[str, str],
    trips: Mapping[str, str],
) -> str:
    """Return source-scoped mapping of company IDs to generated internal IDs."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("source_system", "record_type", "company_source_id", "internal_id"))
    for kind, mapping in (("user", users), ("trip", trips)):
        for source_id, internal_id in sorted(mapping.items()):
            writer.writerow((source_system, kind, source_id, internal_id))
    return output.getvalue()


def write_id_mapping(path: str | Path, contents: str) -> None:
    """Write a completed import mapping to an explicit operator-selected path."""
    target = Path(path)
    try:
        with target.open("x", encoding="utf-8", newline="") as output:
            output.write(contents)
    except FileExistsError as exc:
        raise FileExistsError(f"refusing to overwrite existing mapping file: {target}") from exc
