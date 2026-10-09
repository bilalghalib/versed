export type CourseMaterialRow = {
  id: string;
  course_id: string;
  book_id: string | null;
  title_override: string | null;
  week_number: number | null;
  sequence_order: number | null;
  is_required: boolean | null;
  books?: {
    id: string;
    title: string;
    author: string | null;
    status: string | null;
  } | null;
};

export type LibraryMaterial = {
  id: string;
  courseId: string;
  bookId: string | null;
  title: string;
  author: string | null;
  weekNumber: number | null;
  sequenceOrder: number;
  isRequired: boolean;
};

/** Columns the library API must select from course_materials. */
export const COURSE_MATERIAL_LIBRARY_SELECT = `
  id,
  course_id,
  book_id,
  title_override,
  week_number,
  is_required,
  sequence_order,
  books (
    id, title, author, pdf_url, status
  )
`.trim();

export function mapCourseMaterial(row: CourseMaterialRow): LibraryMaterial {
  return {
    id: row.id,
    courseId: row.course_id,
    bookId: row.book_id,
    title: row.title_override?.trim() || row.books?.title || "Untitled reading",
    author: row.books?.author ?? null,
    weekNumber: row.week_number == null ? null : Number(row.week_number),
    sequenceOrder: row.sequence_order == null ? 0 : Number(row.sequence_order),
    isRequired: row.is_required !== false,
  };
}

export type WeekGroup = {
  weekNumber: number | null;
  label: string;
  required: LibraryMaterial[];
  optional: LibraryMaterial[];
};

export function groupReadingsByWeek(materials: LibraryMaterial[]): WeekGroup[] {
  const byWeek = new Map<number | "none", LibraryMaterial[]>();
  const sorted = [...materials].sort((a, b) => {
    const weekA = a.weekNumber ?? Number.POSITIVE_INFINITY;
    const weekB = b.weekNumber ?? Number.POSITIVE_INFINITY;
    if (weekA !== weekB) return weekA - weekB;
    if (a.sequenceOrder !== b.sequenceOrder) return a.sequenceOrder - b.sequenceOrder;
    return a.title.localeCompare(b.title);
  });
  for (const material of sorted) {
    const key = material.weekNumber == null ? "none" : material.weekNumber;
    const list = byWeek.get(key) ?? [];
    list.push(material);
    byWeek.set(key, list);
  }
  return [...byWeek.entries()].map(([key, rows]) => {
    const weekNumber = key === "none" ? null : key;
    return {
      weekNumber,
      label: weekNumber == null ? "Ungrouped" : `Week ${weekNumber}`,
      required: rows.filter((row) => row.isRequired),
      optional: rows.filter((row) => !row.isRequired),
    };
  });
}
