/**
 * Super admin (Bilal / Versed) and CMC teacher admin are different desks.
 * Production already rewrites /admin → sourced-super-admin on the global app.
 * On cmc.versed.page, /admin is the CMC teacher login instead.
 */

import { isCmcHost } from "./host.ts";

export type AdminSurface = "super-admin" | "cmc-teacher" | "none";

export type AdminIdentity = {
  email: string | null;
  isSuperAdmin: boolean;
  isCmcTeacher: boolean;
};

export function resolveAdminSurface(input: {
  hostname: string;
  pathname: string;
  identity: AdminIdentity;
}): AdminSurface {
  const path = normalizePath(input.pathname);
  const cmc = isCmcHost(input.hostname);

  if (cmc) {
    if (path === "/admin" || path.startsWith("/admin/")) return "cmc-teacher";
    if (path === "/sourced-super-admin" || path.startsWith("/sourced-super-admin/")) {
      return input.identity.isSuperAdmin ? "super-admin" : "none";
    }
    return "none";
  }

  if (path === "/admin" || path === "/sourced-super-admin" || path.startsWith("/sourced-super-admin/")) {
    return input.identity.isSuperAdmin ? "super-admin" : "none";
  }
  return "none";
}

export function adminLoginCopy(surface: AdminSurface): {
  title: string;
  subtitle: string;
  cta: string;
} {
  if (surface === "cmc-teacher") {
    return {
      title: "CMC teacher desk",
      subtitle: "Sign in to manage the Islamic Psychology Program — content, questions, and who can join.",
      cta: "Sign in to teach",
    };
  }
  if (surface === "super-admin") {
    return {
      title: "Versed super admin",
      subtitle: "Global catalog, processing, and every organization. This is not the CMC teacher desk.",
      cta: "Sign in as super admin",
    };
  }
  return {
    title: "Admin",
    subtitle: "You don’t have access to this desk.",
    cta: "Back",
  };
}

export function canOpenCmcTeacherDesk(identity: AdminIdentity): boolean {
  return identity.isCmcTeacher || identity.isSuperAdmin;
}

function normalizePath(pathname: string): string {
  const path = pathname.split("?")[0]?.split("#")[0] ?? "/";
  if (path.length > 1 && path.endsWith("/")) return path.slice(0, -1);
  return path || "/";
}
