from __future__ import annotations

from types import SimpleNamespace

from app.persistence import postgres_reader


def test_chat_adapter_fills_missing_sequence_and_keeps_string_message_id(monkeypatch):
    rows = [
        SimpleNamespace(
            message_id="EV-000005",
            ride_id="RIDE-000001",
            participant_role="driver",
            sent_at=None,
            message_text="On my way.",
            sequence_no=None,
            message_type="message",
            source_system=None,
            evidence_source=None,
            verification_status="verified",
            verified_by=None,
            verified_at=None,
            provenance={},
        ),
        SimpleNamespace(
            message_id="EV-000006",
            ride_id="RIDE-000001",
            participant_role="rider",
            sent_at=None,
            message_text="Thank you.",
            sequence_no=3,
            message_type="message",
            source_system=None,
            evidence_source=None,
            verification_status="verified",
            verified_by=None,
            verified_at=None,
            provenance={},
        ),
    ]
    monkeypatch.setattr(postgres_reader, "db_get_chat_log", lambda _ride_id: rows)

    messages = postgres_reader.PostgresReader("postgresql://unused").get_chat_log(
        "RIDE-000001"
    ).messages

    assert [message.seq for message in messages] == [1, 3]
    assert [message.message_id for message in messages] == ["EV-000005", "EV-000006"]


def test_archive_adapter_preserves_model_and_reviewer_rulings(monkeypatch):
    from decimal import Decimal

    decision = SimpleNamespace(
        ruling_type="refund", recommended_action_description="Refund S$5",
        confidence=Decimal("0.8"), decision_origin="human", decided_at=None,
    )
    model_ruling = SimpleNamespace(
        stage="model_proposed", decision=SimpleNamespace(
            ruling_type="no_action", recommended_action_description="No action",
            confidence=Decimal("0.6"), decision_origin="agent", decided_at=None,
        ),
    )
    reviewer_ruling = SimpleNamespace(stage="reviewer_approved", decision=decision)
    result = SimpleNamespace(
        archive_case_id="DSP-000101", category="fare_calculation",
        decision=decision, policy_version="policy-1", feature_vector={},
        rulings=[model_ruling, reviewer_ruling],
    )
    monkeypatch.setattr(postgres_reader, "db_search_archive", lambda *_args: [result])

    cases = postgres_reader.PostgresReader("postgresql://unused").search_archive(
        "fare_calculation", {}, 3
    )

    assert [ruling["stage"] for ruling in cases[0].rulings] == [
        "model_proposed", "reviewer_approved"
    ]
    assert [ruling["decision_origin"] for ruling in cases[0].rulings] == ["agent", "human"]
    assert cases[0].rulings[1]["recommended_action"] == "Refund S$5"


def test_archive_case_lookup_uses_only_archive_accessor_with_canonical_id(monkeypatch):
    decision = SimpleNamespace(
        ruling_type="refund", recommended_action_description="Refund S$5",
        confidence=0.8, decision_origin="human",
    )
    archived = SimpleNamespace(
        archive_case_id="DSP-123456", category="fare_calculation", decision=decision,
        policy_version="policy-1", human_review=SimpleNamespace(human_reviewed=True),
        rulings=[], feature_vector={},
    )
    looked_up = []

    def get_archive_case(case_id):
        looked_up.append(case_id)
        return archived

    monkeypatch.setattr(postgres_reader, "db_get_archive_case", get_archive_case)
    result = postgres_reader.PostgresReader("postgresql://unused").get_archive_case(
        "DSP-123456"
    )

    assert looked_up == ["DSP-123456"]
    assert result is not None and result.archive_case_id == "DSP-123456"
