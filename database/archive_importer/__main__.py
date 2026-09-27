"""Validate and import a separate archived-case history ZIP."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

from .bundle import ArchiveBundleError, load_bundle
from .persist import import_bundle

DEFAULT_DATABASE_URL = "postgresql:///ryde_tribunal"


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m archive_importer")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "import"):
        item = sub.add_parser(command)
        item.add_argument("archive", type=Path)
        if command == "import":
            item.add_argument("--database-url", default=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
            item.add_argument("--mapping-out", type=Path)
    args = parser.parse_args()
    try:
        bundle = load_bundle(args.archive)
        if args.command == "validate":
            print(
                "Valid synthetic archive bundle: "
                f"{len(bundle.tables['users.csv'])} users, {len(bundle.tables['trips.csv'])} trips, "
                f"{len(bundle.tables['cases.csv'])} cases"
            )
            return 0
        if args.mapping_out and args.mapping_out.exists():
            raise FileExistsError(f"mapping output already exists: {args.mapping_out}")
        result = import_bundle(args.database_url, bundle)
        if args.mapping_out:
            if not args.mapping_out.parent.is_dir():
                raise FileNotFoundError(f"mapping output folder does not exist: {args.mapping_out.parent}")
            args.mapping_out.write_text(result.mapping_csv, encoding="utf-8")
        else:
            sys.stdout.write(result.mapping_csv)
        print(
            f"Archive import complete: {result.imported_users} users, {result.imported_trips} trips, "
            f"{result.imported_cases} cases added.", file=sys.stderr
        )
        return 0
    except (ArchiveBundleError, ValueError, OSError) as exc:
        print(f"Archive import stopped: {exc}", file=sys.stderr)
        return 2
    except psycopg.Error as exc:
        print(f"Database archive import failed ({type(exc).__name__}); transaction rolled back.", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
