"use client";
import { useState, useId } from "react";
import { getActiveClient } from "@/lib/api/fixture-client";
import type { PolicyDocument } from "@/lib/api/types";

import { policyLabel } from "@/lib/review-copy";

type Rule = PolicyDocument["rules"][number];
export function PolicyReference({ ruleId, version }: { ruleId: string; version?: string }) {
  const detailId = useId();
  const [open, setOpen] = useState(false);
  const [rule, setRule] = useState<Rule | null>(null);
  const [error, setError] = useState("");
  async function toggle() {
    setOpen(!open);
    if (!open && !rule) {
      if (!version) { setError("Policy version is unavailable for this recorded example."); return; }
      try {
        const document = await getActiveClient().getPolicy(version);
        if (document.version !== version) throw new Error("The requested historical policy is unavailable in this example.");
        const found = document.rules.find(item => item.id === ruleId);
        if (!found) throw new Error("Rule is unavailable in this policy version.");
        setRule(found);
      } catch (cause) { setError(cause instanceof Error ? cause.message : "Policy could not be loaded."); }
    }
  }
  return <span className="policy-reference"><button type="button" onClick={toggle} aria-expanded={open} aria-controls={detailId} className="policy-chip" title={ruleId}>{policyLabel(ruleId)}</button>
    {open && <span id={detailId} className="policy-popover" role="status">{error || (!rule ? "Loading policy…" : <>
      <strong>{rule.classification === "ryde_policy" ? "Ryde published policy" : rule.classification === "tribunal_operating_rule" ? "Tribunal operating rule" : "Historical fictional policy"}</strong>
      <span>{rule.text}</span>{rule.source && <a href={rule.source.url} target="_blank" rel="noreferrer">{rule.source.title} ↗</a>}
      <small>{ruleId} · Version {version}{rule.source ? ` · Retrieved ${rule.source.retrieved_at}` : ""}</small>
    </>)}</span>}
  </span>;
}
