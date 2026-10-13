import json
from pathlib import Path

def test_official_rules_have_sources_and_operating_rules_are_distinct():
    policy = json.loads((Path(__file__).parents[1] / "seed/policy/ryde-policy-1.0.0.json").read_text())
    assert len({r["id"] for r in policy["rules"]}) == len(policy["rules"])
    for rule in policy["rules"]:
        if rule["classification"] == "ryde_policy":
            assert rule["source"]["url"].startswith("https://help.rydesharing.com/")
            assert rule["source"]["retrieved_at"] == "2026-10-13"
        else:
            assert "source" not in rule
    assert {t["name"]: t["value"] for t in policy["numeric_thresholds"]}["driver_wait_seconds"] == 180
    assert all(t["name"] != "route_deviation_pct" for t in policy["numeric_thresholds"])
