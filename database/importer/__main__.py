"""Command line interface for company CSV ZIP imports."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

from .bundle import BundleValidationError, load_bundle
from .mapping import write_id_mapping
from .persist import ImportDataError, import_bundle


DEFAULT_DATABASE_URL = "postgresql:///ryde_tribunal"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m importer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "import"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("archive", type=Path, help="ZIP file containing the company CSV bundle")
        if command == "import":
            subparser.add_argument(
                "--database-url",
                default=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
                help="PostgreSQL DSN (defaults to DATABASE_URL or the local database)",
            )
            subparser.add_argument(
                "--mapping-out",
                type=Path,
                help="write source-to-generated-ID mapping CSV here; defaults to standard output",
            )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        bundle = load_bundle(args.archive)
        if args.command == "validate":
            print(
                "Valid company bundle: "
                f"{len(bundle.tables['users.csv'])} users, "
                f"{len(bundle.tables['trips.csv'])} trips, "
                f"{len(bundle.tables['gps_telemetry.csv'])} GPS rows, "
                f"{len(bundle.tables['chat_logs.csv'])} chat rows, "
                f"{len(bundle.tables['app_events.csv'])} app events"
            )
            return 0
        if args.mapping_out is not None and args.mapping_out.exists():
            raise FileExistsError(f"mapping output already exists: {args.mapping_out}")
        if args.mapping_out is not None and not args.mapping_out.parent.is_dir():
            raise FileNotFoundError(f"mapping output folder does not exist: {args.mapping_out.parent}")
        result = import_bundle(args.database_url, bundle)
        if args.mapping_out is None:
            sys.stdout.write(result.mapping_csv)
        else:
            write_id_mapping(args.mapping_out, result.mapping_csv)
        print(
            f"Import complete: added {result.imported_user_count} users and "
            f"{result.imported_trip_count} trips; skipped {len(result.skipped_user_ids)} existing users "
            f"and {len(result.skipped_trip_ids)} existing trips.",
            file=sys.stderr,
        )
        for label, ids in (("user", result.skipped_user_ids), ("trip", result.skipped_trip_ids)):
            if ids:
                print(f"Skipped existing {label} IDs: {', '.join(ids)}", file=sys.stderr)
        if args.mapping_out is not None:
            print(f"ID mapping written to {args.mapping_out}", file=sys.stderr)
        return 0
    except (BundleValidationError, ImportDataError, OSError) as exc:
        print(f"Import stopped: {exc}", file=sys.stderr)
        return 2
    except psycopg.Error as exc:
        # Database drivers may include bound values in exception text; avoid echoing imported data.
        print(f"Database import failed ({type(exc).__name__}); transaction rolled back.", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
