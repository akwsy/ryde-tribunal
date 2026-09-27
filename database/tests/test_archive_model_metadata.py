from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from reader.models import (
    ArchiveCase,
    ArchiveDecision,
    ArchiveTripSnapshot,
    ArchiveUserSnapshot,
    HumanReview,
    Money,
)


def test_archive_case_accepts_import_metadata_selected_by_accessor() -> None:
    # get_archive_case selects c.*; these two columns are part of that row and must remain
    # available to the accessor/detail snapshot rather than causing strict validation to fail.
    archived = ArchiveCase.model_validate(
        {
            "archive_case_id": "DSP-000046",
            "archive_ride_id": "RIDE-000046",
            "filing_archive_user_id": "USR-R-000046",
            "bundle_case_key": "sample-bundle:case-46",
            "category": "no_show_charge",
            "subject": "Disputed cancellation fee",
            "filed_by": "rider",
            "created_at": datetime(2026, 8, 1, tzinfo=UTC),
            "policy_version": "ryde-policy-0.1.2",
            "primary_classification": "fee_not_supported",
            "secondary_classifications": [],
            "monetary_impact": Money(amount_cents=1500, currency="SGD"),
            "fraud_risk": Decimal("0"),
            "evidence": [],
            "decision": ArchiveDecision.model_construct(),
            "rulings": [],
            "trip_snapshot": ArchiveTripSnapshot.model_construct(),
            "filing_user_snapshot": ArchiveUserSnapshot.model_construct(),
            "human_review": HumanReview.model_construct(),
            "synthetic": True,
        }
    )

    assert archived.filing_archive_user_id == "USR-R-000046"
    assert archived.bundle_case_key == "sample-bundle:case-46"
