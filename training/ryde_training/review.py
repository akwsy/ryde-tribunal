"""Validate owner-reviewed targets and export only approved core-agent labels."""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from .generate import ROLES, VERSION, outside_repository

DECISIONS = {"approve", "correct", "reject", "pending"}


def _approval_metadata(record, label):
    decision = str(record.get("decision", "pending")).strip().lower()
    if decision not in DECISIONS:
        raise ValueError(f"{label}: unknown review decision")
    if decision not in {"approve", "correct"}:
        return decision
    if not str(record.get("reviewer") or "").strip():
        raise ValueError(f"{label}: reviewer is required for approval")
    if not str(record.get("rationale") or "").strip():
        raise ValueError(f"{label}: rationale is required for approval")
    if record.get("policy_version") != VERSION:
        raise ValueError(f"{label}: stale policy label")
    try:
        approved = datetime.fromisoformat(str(record.get("reviewed_at", "")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}: timezone-aware review timestamp required") from exc
    if approved.tzinfo is None or approved.utcoffset() is None:
        raise ValueError(f"{label}: timezone-aware review timestamp required")
    return decision


def _target_json(target, role, prompt, label):
    messages = target.get("messages") or []
    if not messages or messages[-1].get("role") != "assistant":
        raise ValueError(f"{label}: approved assistant target required")
    try:
        answer = json.loads(messages[-1]["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}: assistant target must be valid JSON") from exc
    if not isinstance(answer, dict):
        raise ValueError(f"{label}: assistant target must be a JSON object")
    rules = prompt.get("policy_rules") or []
    valid_policy_ids = {rule.get("id") for rule in rules if isinstance(rule, dict)}
    references = answer.get("policy_references", [])
    if not isinstance(references, list) or any(not isinstance(ref, str) or ref not in valid_policy_ids for ref in references):
        raise ValueError(f"{label}: policy references must resolve to supplied policy rules")
    evidence = prompt.get("evidence_records") or []
    evidence_by_id = {item.get("evidence_id"): item for item in evidence if isinstance(item, dict)}
    evidence_ids = set(evidence_by_id)
    direct = answer.get("evidence_references", [])
    if not isinstance(direct, list) or any(not isinstance(ref, str) for ref in direct):
        raise ValueError(f"{label}: evidence references must be a list of evidence IDs")
    cited = set(direct)
    citations = []
    for claim in answer.get("claims", []) if isinstance(answer.get("claims", []), list) else []:
        if isinstance(claim, dict):
            claim_citations = claim.get("citations", [])
            if not isinstance(claim_citations, list):
                raise ValueError(f"{label}: claim citations must be a list")
            citations.extend(claim_citations)
    for fact in answer.get("decisive_facts", []) if isinstance(answer.get("decisive_facts", []), list) else []:
        if isinstance(fact, dict):
            fact_refs = fact.get("evidence_references", [])
            fact_citations = fact.get("citations", [])
            if not isinstance(fact_refs, list) or any(not isinstance(ref, str) for ref in fact_refs):
                raise ValueError(f"{label}: decisive fact evidence references must be evidence IDs")
            if not isinstance(fact_citations, list):
                raise ValueError(f"{label}: decisive fact citations must be a list")
            cited.update(fact_refs)
            citations.extend(fact_citations)
    for citation in citations:
        if not isinstance(citation, dict) or not isinstance(citation.get("evidence_id"), str):
            raise ValueError(f"{label}: every citation must name an evidence ID")
        evidence_id = citation["evidence_id"]
        cited.add(evidence_id)
        path = citation.get("field_path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"{label}: every citation must identify a field path")
        value = evidence_by_id.get(evidence_id, {}).get("payload")
        tokens = [match.group(1) or match.group(2)
                  for match in re.finditer(r"([^\.\[\]]+)|\[(\d+)\]", path)]
        try:
            for token in tokens:
                value = value[int(token)] if isinstance(value, list) else value[token]
        except (KeyError, IndexError, TypeError, ValueError):
            raise ValueError(f"{label}: citation field path does not resolve in evidence")
        if "observed_value" not in citation or citation["observed_value"] != value:
            raise ValueError(f"{label}: citation observed value does not match evidence")
    if cited - evidence_ids:
        raise ValueError(f"{label}: evidence references must resolve to supplied evidence")
    if role in {"rider_advocate", "driver_advocate"}:
        if not isinstance(answer.get("argument"), str) or not isinstance(answer.get("claims"), list):
            raise ValueError(f"{label}: advocate target requires argument and claims")
    elif role == "judge":
        if answer.get("ruling_type") not in {"refund", "no_action", "compensation"}:
            raise ValueError(f"{label}: invalid Judge ruling type")
        action = answer.get("recommended_action")
        confidence = answer.get("confidence")
        if not isinstance(action, dict) or isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError(f"{label}: Judge target requires an action and valid confidence")
        if not isinstance(answer.get("decisive_facts"), list):
            raise ValueError(f"{label}: Judge target requires decisive facts")
    return answer


def export(source, output):
    destination = outside_repository(output)
    destination.mkdir(parents=True, exist_ok=False)
    splits = {split: [] for split in ("train", "validation", "test")}
    families = {}
    ids = set()
    for line_number, line in enumerate(Path(source).read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        sample = row["sample"]
        split = row["split"]
        family = sample["scenario_family"]
        sample_id = sample["sample_id"]
        label = f"line {line_number} ({sample_id})"
        if split not in splits:
            raise ValueError(f"{label}: unknown split")
        if family in families and families[family] != split:
            raise ValueError("Scenario family leakage")
        families[family] = split
        if sample_id in ids:
            raise ValueError("Duplicate sample")
        ids.add(sample_id)
        if sample.get("policy_version") != VERSION:
            raise ValueError(f"{label}: stale policy label")

        ruling_review = row.get("ruling_review") or {}
        ruling_decision = _approval_metadata(ruling_review, f"{label} ruling")
        if ruling_decision not in {"approve", "correct"} or not row.get("approved_ruling"):
            continue
        if row.get("review_status") not in ("resolved", "overridden"):
            raise ValueError(f"{label}: approved ruling needs resolved or overridden status")
        ruling_target = row.get("ruling_target")
        if not isinstance(ruling_target, dict):
            raise ValueError(f"{label}: approved ruling JSON is required")
        judge_prompt = json.loads(row["role_targets"]["judge"]["messages"][0]["content"])
        _validate_standalone_judge(ruling_target, judge_prompt, label)

        for role in ROLES:
            target = row.get("role_targets", {}).get(role)
            if not target:
                raise ValueError(f"{label}: missing core role target {role}")
            target_review = target.get("review") or {}
            decision = _approval_metadata(target_review, f"{label} {role}")
            if decision not in {"approve", "correct"} or not target.get("approved"):
                continue
            if target.get("origin") != "human_reviewed":
                raise ValueError(f"{label} {role}: only human-reviewed targets can train")
            prompt = json.loads(target["messages"][0]["content"])
            answer = _target_json(target, role, prompt, f"{label} {role}")
            splits[split].append({
                "prompt": target["messages"][:-1],
                "completion": [{"role": "assistant", "content": json.dumps(answer, sort_keys=True)}],
                "role": role,
                "sample_id": sample_id,
                "scenario_family": family,
            })
    if not splits["train"]:
        raise ValueError("No human-approved training examples; export stopped")
    for split, rows in splits.items():
        (destination / f"{split}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return {split: len(rows) for split, rows in splits.items()}


def _validate_standalone_judge(answer, prompt, label):
    target = {"messages": [{"role": "user", "content": json.dumps(prompt)},
                           {"role": "assistant", "content": json.dumps(answer)}]}
    _target_json(target, "judge", prompt, f"{label} ruling")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(export(args.source, args.output))
