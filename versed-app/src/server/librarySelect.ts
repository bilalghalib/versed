import { COURSE_MATERIAL_LIBRARY_SELECT, mapCourseMaterial, type CourseMaterialRow } from "../lib/groupReadings.ts";

type QueryBuilder = {
  from: (table: string) => {
    select: (columns: string) => {
      eq: (column: string, value: string) => {
        order: (column: string, options: { ascending: boolean }) => Promise<{
          data: CourseMaterialRow[] | null;
          error: { message: string } | null;
        }> & {
          order: (column: string, options: { ascending: boolean }) => Promise<{
            data: CourseMaterialRow[] | null;
            error: { message: string } | null;
          }>;
        };
      };
    };
  };
};

export { COURSE_MATERIAL_LIBRARY_SELECT };

export async function fetchCourseReadings(
  supabase: QueryBuilder,
  courseId: string,
): Promise<ReturnType<typeof mapCourseMaterial>[]> {
  const { data, error } = await supabase
    .from("course_materials")
    .select(COURSE_MATERIAL_LIBRARY_SELECT)
    .eq("course_id", courseId)
    .order("week_number", { ascending: true })
    .order("sequence_order", { ascending: true });

  if (error) throw new Error(error.message);
  return (data ?? []).map(mapCourseMaterial);
}

export function attachReadingsToLibraryBooks<T extends { id?: string; book?: { id?: string } | null }>(
  books: T[],
  readings: ReturnType<typeof mapCourseMaterial>[],
): Array<T & { weekNumber: number | null; isRequired: boolean }> {
  const byBook = new Map(readings.map((row) => [row.bookId, row]));
  return books.map((item) => {
    const bookId = item.book?.id ?? item.id ?? null;
    const reading = bookId ? byBook.get(bookId) : undefined;
    return {
      ...item,
      weekNumber: reading?.weekNumber ?? null,
      isRequired: reading?.isRequired ?? true,
    };
  });
}
