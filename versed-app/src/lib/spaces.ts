/**
 * Spaces, not hostnames, decide what a student sees.
 *
 * CMC class readings follow the enrollment, everywhere: cmc.versed.page,
 * versed.page, and later the iPhone app. A host is only a branded default.
 *
 *   Islamic Psychology  — program only (class readings, no personal PDFs)
 *   My library          — program + the student's own uploads
 */

import { CMC_PROGRAM_CODE, CMC_PROGRAM_NAME, isCmcHost } from "./host.ts";

export const SPACE_STORAGE_KEY = "versed.activeSpace";

export type SpaceId = "cmc-program" | "library";

export type Space = {
  id: SpaceId;
  label: string;
  hint: string;
  showProgram: boolean;
  showPersonalUploads: boolean;
};

export const CMC_PROGRAM_SPACE: Space = {
  id: "cmc-program",
  label: CMC_PROGRAM_NAME,
  hint: "Class readings for this program",
  showProgram: true,
  showPersonalUploads: false,
};

export const LIBRARY_SPACE: Space = {
  id: "library",
  label: "My library",
  hint: "Class readings plus your uploads",
  showProgram: true,
  showPersonalUploads: true,
};

export function spacesForStudent(input: { enrolledInCmc: boolean }): Space[] {
  if (input.enrolledInCmc) return [CMC_PROGRAM_SPACE, LIBRARY_SPACE];
  return [LIBRARY_SPACE];
}

/** Host is a default, never a lock. Preferred space (app toggle) wins. */
export function defaultSpaceId(input: {
  hostname?: string;
  preferred?: SpaceId | null;
  enrolledInCmc: boolean;
}): SpaceId {
  if (input.preferred && spaceIsAvailable(input.preferred, input.enrolledInCmc)) {
    return input.preferred;
  }
  if (input.enrolledInCmc && input.hostname && isCmcHost(input.hostname)) {
    return "cmc-program";
  }
  return "library";
}

export function spaceById(id: SpaceId, enrolledInCmc: boolean): Space {
  const available = spacesForStudent({ enrolledInCmc });
  return available.find((space) => space.id === id) ?? LIBRARY_SPACE;
}

export function filterLibraryForSpace<TProgram, TUpload>(input: {
  space: Space;
  programs: TProgram[];
  personalUploads: TUpload[];
}): { programs: TProgram[]; personalUploads: TUpload[] } {
  return {
    programs: input.space.showProgram ? input.programs : [],
    personalUploads: input.space.showPersonalUploads ? input.personalUploads : [],
  };
}

function spaceIsAvailable(id: SpaceId, enrolledInCmc: boolean): boolean {
  return spacesForStudent({ enrolledInCmc }).some((space) => space.id === id);
}

export { CMC_PROGRAM_CODE };
