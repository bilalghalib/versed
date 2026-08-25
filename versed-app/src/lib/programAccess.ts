import { normalizeEmail } from "./emails.ts";

export type RequestStatus = "pending" | "approved" | "denied";

export type JoinGate =
  | { status: "enter"; reason: "already_enrolled" | "allowlisted" }
  | { status: "request"; reason: "not_allowlisted" }
  | { status: "pending"; reason: "request_pending" }
  | { status: "denied"; reason: "request_denied" }
  | { status: "blocked"; reason: "not_signed_in" };

export function canEnrollInProgram(input: {
  email: string | null | undefined;
  allowlist: readonly string[];
  alreadyEnrolled: boolean;
  requestStatus?: RequestStatus | null;
}): JoinGate {
  if (input.alreadyEnrolled) return { status: "enter", reason: "already_enrolled" };
  const email = normalizeEmail(input.email);
  if (!email) return { status: "blocked", reason: "not_signed_in" };

  const listed = new Set(input.allowlist.map((item) => item.trim().toLowerCase()));
  if (listed.has(email) || input.requestStatus === "approved") {
    return { status: "enter", reason: "allowlisted" };
  }
  if (input.requestStatus === "pending") return { status: "pending", reason: "request_pending" };
  if (input.requestStatus === "denied") return { status: "denied", reason: "request_denied" };
  return { status: "request", reason: "not_allowlisted" };
}

/** Join code is not authorization. Empty allowlist + no approval = nobody new. */
export function allowlistIsAuthorization(allowlist: readonly string[]): boolean {
  return allowlist.length > 0;
}
