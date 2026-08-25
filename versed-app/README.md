# CMC student + teacher UX (remaining slice)

This folder is the CMC program slice for **versed-app**. This Cloud Agent session
was attached to public `github.com/bilalghalib/versed` (PDF tooling). The private
app repo was not installed on the GitHub App, so the slice lives here as a drop-in
for `github.com/bilalghalib/versed-app`.

Do not apply the SQL on live Supabase from the agent. Do not run the extract
pipeline, routing canary, or Scaleway jobs.

## What this adds

1. **Spaces, not URLs.** CMC class readings follow enrollment on every host and later the iPhone app.
   `cmc.versed.page` defaults to the Islamic Psychology space. `versed.page` defaults
   to **My library** (class + personal uploads). A space toggle switches between them.
2. Access is an **email allowlist** and/or a **request a teacher approves**. A join code is not enough.
2. Student course list: **Week** rows with **Required / Optional**, from
   `course_materials.week_number` and `is_required`.
3. Teacher program tabs: **Overview | Content | Questions | Settings**.
   Per-course tools stay behind **Manage course**.
4. Questions use `book_comments` (`kind/status/page/block/word/selected_text/color`)
   with amber + `?` + **Question**. Sharing with the class is optional.
   Private highlights stay owner-only. `shared_annotations_enabled` cascades
   course → program → org → false.
5. **Two admin desks.** Super admin (Bilal) stays on `versed.page/admin`
   (existing sourced-super-admin). CMC teachers get a custom
   **`cmc.versed.page/admin`** login that never opens catalog / quality / runs.

## Run

```bash
cd versed-app
npm test
npx tsc --noEmit
npm run preview   # http://127.0.0.1:4173/
```

## Bilal must apply remotely

- `supabase/migrations/20260825140000_program_join_allowlist_and_requests.sql`
- `supabase/migrations/20260825140100_book_comments_questions.sql`
- Existing `20260823133911_add_program_enrollment.sql` if not already on prod
- `tools/bootstrap_cmc.sql` (turns shared annotations on for CMC; seed real student emails yourself)
- DNS/host already serving `cmc.versed.page` — keep it pointed at the app
- GitHub App access to private `versed-app` so this can merge there
