import type { Evidence } from "@/lib/api/types";

/**
 * FIXTURE — not production data. All data is synthetic.
 *
 * Chat log evidence: verified, no uncertainty_pct (the "absent" case).
 */
export const evidenceChatLog: Evidence = {
  evidence_id: "EV-000790",
  case_id: "DSP-000045",
  class: "chat_log",
  source: "system_record",
  recorded_at: "2026-09-22T06:38:00Z",
  provenance: {
    table: "ride_chat_messages",
    row_ids: ["msg-001", "msg-002"],
    collector: "app_v3",
  },
  verification: {
    status: "verified",
    method: "platform_message_log",
    // uncertainty_pct is intentionally absent — the UI must handle this case.
  },
  visibility: "both",
  payload: {
    messages: [
      {
        role: "rider",
        timestamp: "2026-09-22T06:38:00Z",
        text: "I'm at the pickup point.",
      },
      {
        role: "driver",
        timestamp: "2026-09-22T06:42:00Z",
        text: "On my way, there's some traffic.",
      },
    ],
    message_count: 2,
    route_change_requested: false,
  },
};
