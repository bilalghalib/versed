import { canEnrollInProgram, type RequestStatus } from "../lib/programAccess.ts";
import { normalizeEmail } from "../lib/emails.ts";
import { resolveProgramFromHost } from "../lib/host.ts";

export type JoinProgramResult =
  | { ok: true; kind: "program"; alreadyEnrolled: boolean; programId: string }
  | { ok: false; error: string; gate: ReturnType<typeof canEnrollInProgram> };

export async function decideProgramJoin(input: {
  hostname?: string;
  email: string | null;
  allowlist: string[];
  alreadyEnrolled: boolean;
  requestStatus?: RequestStatus | null;
  joinCode?: string | null;
}): Promise<JoinProgramResult> {
  const hostProgram = input.hostname ? resolveProgramFromHost(input.hostname) : null;
  if (!hostProgram && !input.joinCode) {
    return {
      ok: false,
      error: "This program is available at cmc.versed.page or with an invite.",
      gate: { status: "blocked", reason: "not_signed_in" },
    };
  }

  const gate = canEnrollInProgram({
    email: input.email,
    allowlist: input.allowlist,
    alreadyEnrolled: input.alreadyEnrolled,
    requestStatus: input.requestStatus,
  });

  if (gate.status === "enter") {
    return {
      ok: true,
      kind: "program",
      alreadyEnrolled: gate.reason === "already_enrolled",
      programId: hostProgram?.code ?? "program",
    };
  }

  const error =
    gate.status === "pending"
      ? "Your request was sent. We’ll add you when it’s approved."
      : gate.status === "denied"
        ? "This request wasn’t approved yet. Ask your teacher."
        : gate.status === "blocked"
          ? "Sign in with the email your teacher listed."
          : "This program is for invited students. You can request access.";

  return { ok: false, error, gate };
}

export function enrollWithoutOrgMembership(input: {
  userId: string;
  programId: string;
  email: string;
}): { userId: string; programId: string; orgMember: false; email: string } {
  const email = normalizeEmail(input.email);
  if (!email) throw new Error("A valid email is required.");
  return {
    userId: input.userId,
    programId: input.programId,
    orgMember: false,
    email,
  };
}
