from __future__ import annotations

import pytest

from tests.conftest import require_test_database_name


def test_database_target_guard_accepts_explicit_test_database() -> None:
    assert require_test_database_name("postgresql:///ryde_tribunal_test") == "ryde_tribunal_test"
    assert require_test_database_name("postgresql:///ryde_tribunal_tests") == "ryde_tribunal_tests"


@pytest.mark.parametrize(
    "database_url",
    ["postgresql:///ryde_tribunal", "postgresql:///postgres", "postgresql:///ryde-test"],
)
def test_database_target_guard_refuses_non_test_database(database_url: str) -> None:
    with pytest.raises(ValueError, match="ending in '_test' or '_tests'"):
        require_test_database_name(database_url)
