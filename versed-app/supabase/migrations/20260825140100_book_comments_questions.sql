-- Shared questions via book_comments.
-- Private annotations stay owner-only. Shared ones are optional.
-- Cascade default is off (course → program → org → false).
-- Do not apply remotely from this agent.

alter table public.book_comments
  add column if not exists kind text,
  add column if not exists status text,
  add column if not exists page integer,
  add column if not exists block text,
  add column if not exists word text,
  add column if not exists selected_text text,
  add column if not exists color text,
  add column if not exists visibility text,
  add column if not exists answer text,
  add column if not exists course_id uuid,
  add column if not exists program_id uuid,
  add column if not exists org_id uuid;

update public.book_comments
set kind = coalesce(kind, 'highlight'),
    status = coalesce(status, 'open'),
    visibility = coalesce(visibility, 'private')
where kind is null or status is null or visibility is null;

alter table public.book_comments
  alter column kind set default 'highlight',
  alter column status set default 'open',
  alter column visibility set default 'private';

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'book_comments_kind_check'
  ) then
    alter table public.book_comments
      add constraint book_comments_kind_check
      check (kind in ('highlight', 'question'));
  end if;
  if not exists (
    select 1 from pg_constraint where conname = 'book_comments_status_check'
  ) then
    alter table public.book_comments
      add constraint book_comments_status_check
      check (status in ('open', 'answered', 'closed'));
  end if;
  if not exists (
    select 1 from pg_constraint where conname = 'book_comments_visibility_check'
  ) then
    alter table public.book_comments
      add constraint book_comments_visibility_check
      check (visibility in ('private', 'shared'));
  end if;
end $$;

alter table public.courses
  add column if not exists shared_annotations_enabled boolean;
alter table public.programs
  add column if not exists shared_annotations_enabled boolean;
alter table public.organizations
  add column if not exists shared_annotations_enabled boolean;

create or replace function public.shared_annotations_enabled_for(
  p_course_id uuid default null,
  p_program_id uuid default null,
  p_org_id uuid default null
)
returns boolean
language sql
stable
as $$
  select coalesce(
    (select c.shared_annotations_enabled from public.courses c where c.id = p_course_id),
    (select p.shared_annotations_enabled from public.programs p where p.id = p_program_id),
    (select o.shared_annotations_enabled from public.organizations o where o.id = p_org_id),
    false
  );
$$;

alter table public.book_comments enable row level security;

drop policy if exists book_comments_owner_select on public.book_comments;
create policy book_comments_owner_select
  on public.book_comments
  for select
  using (
    user_id = auth.uid()
    or (
      visibility = 'shared'
      and public.shared_annotations_enabled_for(course_id, program_id, org_id)
    )
  );

drop policy if exists book_comments_owner_insert on public.book_comments;
create policy book_comments_owner_insert
  on public.book_comments
  for insert
  with check (user_id = auth.uid());

drop policy if exists book_comments_owner_update on public.book_comments;
create policy book_comments_owner_update
  on public.book_comments
  for update
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- Teachers may answer a shared class question without seeing private highlights.
drop policy if exists book_comments_teacher_answer on public.book_comments;
create policy book_comments_teacher_answer
  on public.book_comments
  for update
  using (
    visibility = 'shared'
    and kind = 'question'
    and exists (
      select 1
      from public.organization_members m
      where m.user_id = auth.uid()
        and m.status = 'active'
        and m.role in ('admin', 'owner', 'instructor', 'teacher')
        and (org_id is null or m.org_id = org_id)
    )
  )
  with check (
    visibility = 'shared'
    and kind = 'question'
  );

drop policy if exists book_comments_owner_delete on public.book_comments;
create policy book_comments_owner_delete
  on public.book_comments
  for delete
  using (user_id = auth.uid());

comment on policy book_comments_owner_select on public.book_comments is
  'Private highlights/questions stay owner-only. Shared rows require the cascade flag.';
