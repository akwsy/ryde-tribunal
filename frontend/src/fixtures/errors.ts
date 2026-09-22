import type { ErrorEnvelope } from "@/lib/api/types";

/**
 * FIXTURE — not production data. All data is synthetic.
 *
 * Error envelopes matching the error contract in docs/02-api-contract.md §1.
 * error.code ∈ validation_error | not_found | conflict | database_unavailable |
 * provider_unavailable | internal_error
 */

export const errorNotFound: ErrorEnvelope = {
  error: {
    code: "not_found",
    message: "Case DSP-000999 not found.",
  },
};

export const errorDatabaseUnavailable: ErrorEnvelope = {
  error: {
    code: "database_unavailable",
    message: "The data layer is unreachable. No ruling can be returned.",
    details: { database: "unavailable" },
  },
};

export const errorInternal: ErrorEnvelope = {
  error: {
    code: "internal_error",
    message: "An internal error occurred while processing the request.",
  },
};

export const errorValidation: ErrorEnvelope = {
  error: {
    code: "validation_error",
    message: "Request validation failed.",
    details: { field: "case_id", issue: "must match pattern ^DSP-\\d{6}$" },
  },
};
