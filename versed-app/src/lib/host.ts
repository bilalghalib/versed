/** Branded hosts. They suggest a default space; they do not hide CMC content. */

export const CMC_HOSTS = new Set([
  "cmc.versed.page",
  "www.cmc.versed.page",
]);

export const CMC_PROGRAM_CODE = "ISLAMIC-PSYCHOLOGY";
export const CMC_PROGRAM_NAME = "Islamic Psychology Program";

export function hostnameFromUrl(url: string | URL | null | undefined): string {
  if (!url) return "";
  try {
    const value = typeof url === "string" ? new URL(url) : url;
    return value.hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return "";
  }
}

export function isCmcHost(hostname: string): boolean {
  const host = hostname.replace(/^www\./, "").toLowerCase();
  return host === "cmc.versed.page" || CMC_HOSTS.has(hostname.toLowerCase());
}

export function resolveProgramFromHost(hostname: string): {
  code: string;
  name: string;
} | null {
  return isCmcHost(hostname) ? { code: CMC_PROGRAM_CODE, name: CMC_PROGRAM_NAME } : null;
}
