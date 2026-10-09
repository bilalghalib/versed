# Wire this slice into versed-app (Expo)

Production already has these surfaces (from the live `cmc.versed.page` bundle).
Extend them; do not replace the library or admin shells.

| Existing | Change |
| --- | --- |
| `GET /api/library` | Select `week_number`, `is_required` from `course_materials`. See `src/server/librarySelect.ts`. |
| `ProgramLibraryOverview` | Tapping C1/C2/C3 opens the week reading list (`src/ui/render.ts#renderStudentReadingList`), not only a flat filter. |
| `POST /api/courses/join` | After resolving the program, call `decideProgramJoin`. Fail closed unless allowlisted or approved. Never insert `organization_members` for students. |
| `JoinClassScreen` | On `cmc.versed.page`, skip the code form and use `renderHostJoin`. |
| `ProgramAdminOverview` | Wrap with tabs Overview / Content / Questions / Settings. Keep **Manage course**. |
| Navigation `/admin` → `sourced-super-admin` | **Host-aware.** See below. |

## Spaces (class vs uploads)

Enrollment, not hostname, decides whether CMC readings appear.

- **Islamic Psychology space** — the nine courses only (what `cmc.versed.page` defaults to).
- **My library space** — those same courses **plus** personal uploads (what `versed.page` defaults to).
- The iPhone app uses the same toggle (`versed.activeSpace`). Switching space works on any host.
- Do not hide the program when the student is on `versed.page`.

`src/lib/spaces.ts` — `defaultSpaceId`, `filterLibraryForSpace`.

## Two admin desks

Today the global app rewrites `/admin` to `sourced-super-admin`. That is Bilal’s
super-admin (catalog, quality, transliterations, orgs, courses, runs).

CMC teachers must not land there.

| Host | Path | Who | Screen |
| --- | --- | --- | --- |
| `cmc.versed.page` | `/admin` | CMC teacher (or Bilal previewing) | Custom login → program tabs |
| `cmc.versed.page` | `/sourced-super-admin` | Super admin only | Existing super admin; 403 for CMC teachers |
| `www.versed.page` | `/admin` or `/sourced-super-admin` | Super admin only | Existing super admin. CMC teachers get “use cmc.versed.page/admin”. |

Use `resolveAdminSurface` in `src/lib/adminAccess.ts`. Do not send CMC staff into
the Organizations/catalog chrome. `canOpenCmcTeacherDesk` is true for CMC
teachers and for super admin (so Bilal can still look at their desk).

The CMC `/admin` login copy is `renderAdminLogin("cmc-teacher")`.

## Host join

`cmc.versed.page` → Islamic Psychology Program (`src/lib/host.ts`).
Students request access; teachers approve on Settings.
