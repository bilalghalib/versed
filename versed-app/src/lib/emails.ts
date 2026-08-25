/** Exact-email helpers for CMC program access. No domain wildcards. */

export function normalizeEmail(raw: string | null | undefined): string | null {
  if (raw == null) return null;
  const email = raw.trim().toLowerCase();
  if (!email) return null;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return null;
  return email;
}

export function parseEmailList(raw: string): { emails: string[]; invalid: string[] } {
  const emails: string[] = [];
  const invalid: string[] = [];
  const seen = new Set<string>();
  for (const piece of raw.split(/[\n,;]+/)) {
    const trimmed = piece.trim();
    if (!trimmed) continue;
    const email = normalizeEmail(trimmed);
    if (!email) {
      invalid.push(trimmed);
      continue;
    }
    if (seen.has(email)) continue;
    seen.add(email);
    emails.push(email);
  }
  return { emails, invalid };
}
