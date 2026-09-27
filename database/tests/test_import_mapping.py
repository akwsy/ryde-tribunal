from __future__ import annotations

import pytest

from importer.mapping import render_id_mapping, write_id_mapping


def test_mapping_contains_only_company_and_generated_ids_in_stable_order():
    result = render_id_mapping(
        source_system="sample-co",
        users={"company-user-b": "USR-D-000001", "company-user-a": "USR-R-000001"},
        trips={"company-trip": "RIDE-000061"},
    )

    assert result == (
        "source_system,record_type,company_source_id,internal_id\n"
        "sample-co,user,company-user-a,USR-R-000001\n"
        "sample-co,user,company-user-b,USR-D-000001\n"
        "sample-co,trip,company-trip,RIDE-000061\n"
    )
    assert "name" not in result
    assert "message" not in result


def test_mapping_writer_requires_new_explicit_path(tmp_path):
    target = tmp_path / "mapping.csv"
    write_id_mapping(target, "header\n")

    assert target.read_text() == "header\n"
    with pytest.raises(FileExistsError):
        write_id_mapping(target, "replacement\n")
