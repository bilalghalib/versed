-- Program join allowlist + requestable access on cmc.versed.page
-- Fail closed: a join code is not authorization.
-- Students enroll as program students, never as organization members.
-- Do not apply this migration on live Supabase from the agent.

create table if not exists public.program_join_allowlist (
  program_id uuid not null references public.programs (id) on delete cascade,
  email text not null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  primary key (program_id, email),
  constraint program_join_allowlist_email_format
    check (email = lower(trim(email)) and email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$')
);

create table if not exists public.program_join_requests (
  id uuid primary key default gen_random_uuid(),
  program_id uuid not null references public.programs (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  email text not null,
  note text,
  status text not null default 'pending'
    check (status in ('pending', 'approved', 'denied')),
  created_at timestamptz not null default now(),
  reviewed_at timestamptz,
  reviewed_by uuid references auth.users (id) on delete set null,
  constraint program_join_requests_email_format
    check (email = lower(trim(email)))
);

create unique index if not exists program_join_requests_one_pending
  on public.program_join_requests (program_id, email)
  where status = 'pending';

alter table public.program_join_allowlist enable row level security;
alter table public.program_join_requests enable row level security;

-- Teachers / org admins manage the list. Students never read other emails.
drop policy if exists program_join_allowlist_teacher_read on public.program_join_allowlist;
create policy program_join_allowlist_teacher_read
  on public.program_join_allowlist
  for select
  using (
    exists (
      select 1
      from public.programs p
      join public.organization_members m on m.org_id = p.org_id
      where p.id = program_id
        and m.user_id = auth.uid()
        and m.role in ('admin', 'owner', 'instructor', 'teacher')
        and m.status = 'active'
    )
  );

drop policy if exists program_join_allowlist_teacher_write on public.program_join_allowlist;
create policy program_join_allowlist_teacher_write
  on public.program_join_allowlist
  for all
  using (
    exists (
      select 1
      from public.programs p
      join public.organization_members m on m.org_id = p.org_id
      where p.id = program_id
        and m.user_id = auth.uid()
        and m.role in ('admin', 'owner', 'instructor', 'teacher')
        and m.status = 'active'
    )
  )
  with check (
    exists (
      select 1
      from public.programs p
      join public.organization_members m on m.org_id = p.org_id
      where p.id = program_id
        and m.user_id = auth.uid()
        and m.role in ('admin', 'owner', 'instructor', 'teacher')
        and m.status = 'active'
    )
  );

drop policy if exists program_join_requests_own_read on public.program_join_requests;
create policy program_join_requests_own_read
  on public.program_join_requests
  for select
  using (
    user_id = auth.uid()
    or exists (
      select 1
      from public.programs p
      join public.organization_members m on m.org_id = p.org_id
      where p.id = program_id
        and m.user_id = auth.uid()
        and m.role in ('admin', 'owner', 'instructor', 'teacher')
        and m.status = 'active'
    )
  );

drop policy if exists program_join_requests_own_insert on public.program_join_requests;
create policy program_join_requests_own_insert
  on public.program_join_requests
  for insert
  with check (
    user_id = auth.uid()
    and email = lower(coalesce(auth.jwt() ->> 'email', ''))
    and status = 'pending'
  );

-- Extend join: allowlist required. Keep tagged program join; do not add org membership.
create or replace function public.email_on_program_allowlist(p_program_id uuid, p_email text)
returns boolean
language sql
stable
as $$
  select exists (
    select 1
    from public.program_join_allowlist a
    where a.program_id = p_program_id
      and a.email = lower(trim(p_email))
  );
$$;

comment on function public.email_on_program_allowlist is
  'Authorization for CMC program join. Join codes are not sufficient.';
