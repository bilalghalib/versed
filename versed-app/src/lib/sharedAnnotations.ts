/**
 * shared_annotations_enabled cascade: course → program → org → false.
 * Spec default is off. CMC bootstrap turns the program on — do not apply live.
 */
export function sharedAnnotationsEnabled(flags: {
  course?: boolean | null;
  program?: boolean | null;
  org?: boolean | null;
}): boolean {
  if (flags.course != null) return flags.course;
  if (flags.program != null) return flags.program;
  if (flags.org != null) return flags.org;
  return false;
}
