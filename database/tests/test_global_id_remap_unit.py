from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "migrate_global_record_ids.py"
SPEC = importlib.util.spec_from_file_location("global_id_remapper", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REMAPPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REMAPPER
SPEC.loader.exec_module(REMAPPER)


def test_archived_identifier_formats_parse_as_their_ordinary_entity_types() -> None:
    assert REMAPPER._suffix("case", "DSP-ARCH-000123") == 123
    assert REMAPPER._suffix("case", "DSP-000123") == 123
    assert REMAPPER._suffix("ride", "RIDE-ARCH-000234") == 234
    assert REMAPPER._suffix("rider", "USR-ARCH-R-000345") == 345
    assert REMAPPER._suffix("driver", "USR-ARCH-D-000456") == 456
    assert REMAPPER._suffix("evidence", "ARCH-EV-000567-02") == 567
    assert REMAPPER._suffix("policy", "ARCH-POLICY-000678") == 678


def test_json_remap_updates_internal_references_but_keeps_company_and_bundle_keys() -> None:
    old_case = "DSP-ARCH-000123"
    old_ride = "RIDE-ARCH-000234"
    old_evidence = "ARCH-EV-000567-02"
    replacements = {
        old_case: "DSP-000901",
        old_ride: "RIDE-000902",
        old_evidence: "EV-000903",
    }
    source = {
        "archive_case_id": old_case,
        "payload": {"archive_ride_id": old_ride},
        "reweighted_evidence": [old_evidence],
        "company_id": old_ride,
        "source_key": old_evidence,
        "bundle_evidence_key": old_evidence,
    }

    changed, did_change = REMAPPER._replace_json(source, replacements)

    assert did_change is True
    assert changed["archive_case_id"] == "DSP-000901"
    assert changed["payload"]["archive_ride_id"] == "RIDE-000902"
    assert changed["reweighted_evidence"] == ["EV-000903"]
    assert changed["company_id"] == old_ride
    assert changed["source_key"] == old_evidence
    assert changed["bundle_evidence_key"] == old_evidence
