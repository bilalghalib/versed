import { colors, type ScreenState } from "./tokens.ts";
import type { WeekGroup } from "../lib/groupReadings.ts";
import { QUESTION_COLOR, QUESTION_LABEL, type BookComment } from "../lib/questions.ts";
import type { JoinGate } from "../lib/programAccess.ts";
import { adminLoginCopy, type AdminSurface } from "../lib/adminAccess.ts";

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function shell(title: string, body: string, options?: { wide?: boolean }): string {
  const max = options?.wide ? "760px" : "390px";
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)}</title>
  <style>
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", Palatino, serif;
      background: ${colors.canvas};
      color: ${colors.text};
    }
    .frame { width: min(100%, 390px); margin: 0 auto; min-height: 100vh; background: ${colors.primary}; }
    .card { background: ${colors.elevated}; border: 1px solid ${colors.border}; border-radius: 20px; padding: 20px; }
    .eyebrow { font-size: 11px; letter-spacing: 1.4px; font-weight: 600; color: ${colors.gold}; text-transform: uppercase; }
    h1 { font-size: 26px; font-weight: 500; margin: 8px 0 0; letter-spacing: -0.4px; }
    p { color: ${colors.textSecondary}; line-height: 1.45; }
    .muted { color: ${colors.muted}; font-size: 13px; }
    .btn { display: block; width: 100%; border: 0; border-radius: 16px; padding: 14px; font-size: 15px; font-weight: 600; cursor: pointer; }
    .btn-primary { background: ${colors.inverse}; color: #FFF8EE; }
    .btn-gold { background: ${colors.gold}; color: #fff; }
    .btn-ghost { background: ${colors.panel}; color: ${colors.text}; }
    input, textarea { width: 100%; border: 1px solid ${colors.border}; border-radius: 14px; padding: 12px 14px; font: inherit; background: ${colors.elevated}; }
    .tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; background: ${colors.secondary}; padding: 6px; border-radius: 14px; }
    .tab { text-align: center; padding: 10px 6px; border-radius: 10px; font-size: 12px; color: ${colors.textSecondary}; }
    .tab.active { background: ${colors.inverse}; color: #FFF8EE; }
    .week { margin-top: 14px; }
    .week-label { font-weight: 600; margin-bottom: 8px; }
    .row { display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid ${colors.border}; }
    .badge { font-size: 11px; letter-spacing: 0.6px; text-transform: uppercase; padding: 4px 8px; border-radius: 999px; }
    .required { background: ${colors.goldSoft}; color: ${colors.gold}; }
    .optional { background: ${colors.panel}; color: ${colors.muted}; }
    .empty { text-align: center; padding: 36px 16px; color: ${colors.textSecondary}; }
    .spinner { width: 28px; height: 28px; border: 3px solid ${colors.goldSoft}; border-top-color: ${colors.gold}; border-radius: 50%; margin: 24px auto; animation: spin 1s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .question { display: flex; gap: 10px; align-items: flex-start; padding: 12px 0; border-bottom: 1px solid ${colors.border}; }
    .qmark { width: 28px; height: 28px; border-radius: 50%; background: ${QUESTION_COLOR}; color: #fff; display: grid; place-items: center; font-weight: 700; flex: none; }
    .qlabel { color: ${QUESTION_COLOR}; font-size: 11px; letter-spacing: 1px; font-weight: 700; text-transform: uppercase; }
    .chip { display: inline-block; font-size: 11px; padding: 3px 8px; border-radius: 999px; background: ${colors.panel}; color: ${colors.muted}; }
  </style>
</head>
<body><div class="frame">${body}</div></body></html>`;
}

export function renderStudentReadingList(input: {
  programName: string;
  term: number;
  componentCode: string;
  courseName: string;
  state: ScreenState;
  weeks?: WeekGroup[];
}): string {
  const pad = `<div style="padding:20px">`;
  if (input.state === "loading") {
    return shell(`${input.courseName} readings`, `${pad}
      <div class="eyebrow">${escapeHtml(input.programName)}</div>
      <h1>Term ${input.term} · ${escapeHtml(input.componentCode)}</h1>
      <div class="spinner" role="status" aria-label="Loading readings"></div>
      <p class="muted" style="text-align:center">Loading this course’s readings…</p>
    </div>`);
  }
  if (input.state === "error") {
    return shell(`${input.courseName} readings`, `${pad}
      <div class="eyebrow">${escapeHtml(input.programName)}</div>
      <h1>Term ${input.term} · ${escapeHtml(input.componentCode)}</h1>
      <div class="empty">We couldn’t load readings for this course. Try again in a moment.</div>
    </div>`);
  }
  const weeks = input.weeks ?? [];
  if (input.state === "empty" || weeks.length === 0) {
    return shell(`${input.courseName} readings`, `${pad}
      <div class="eyebrow">${escapeHtml(input.programName)}</div>
      <h1>${escapeHtml(input.courseName)}</h1>
      <p class="muted">Term ${input.term} · ${escapeHtml(input.componentCode)}</p>
      <div class="card empty">
        <div class="eyebrow">No readings yet</div>
        <p>This course is in the program, but the teacher hasn’t posted weekly readings.</p>
      </div>
    </div>`);
  }
  const weekHtml = weeks.map((week) => {
    const rows = [
      ...week.required.map((item) => ({ item, required: true })),
      ...week.optional.map((item) => ({ item, required: false })),
    ]
      .map(
        ({ item, required }) => `<div class="row">
          <div>
            <div>${escapeHtml(item.title)}</div>
            <div class="muted">${escapeHtml(item.author || "")}</div>
          </div>
          <span class="badge ${required ? "required" : "optional"}">${required ? "Required" : "Optional"}</span>
        </div>`,
      )
      .join("");
    return `<section class="week"><div class="week-label">${escapeHtml(week.label)}</div>${rows || `<div class="muted">No readings this week.</div>`}</section>`;
  }).join("");
  return shell(`${input.courseName} readings`, `${pad}
    <div class="eyebrow">${escapeHtml(input.programName)}</div>
    <h1>${escapeHtml(input.courseName)}</h1>
    <p class="muted">Term ${input.term} · ${escapeHtml(input.componentCode)}</p>
    ${weekHtml}
  </div>`);
}

export function renderCmcTeacherAdmin(input: {
  tab: "overview" | "content" | "questions" | "settings";
  studentCount: number;
  pendingRequests: number;
  emails: string[];
  questions: BookComment[];
  courses: { code: string; name: string; term: number }[];
}): string {
  const tabs = ["overview", "content", "questions", "settings"] as const;
  const tabBar = `<nav class="tabs" aria-label="Program">${tabs
    .map((tab) => `<div class="tab ${tab === input.tab ? "active" : ""}">${tab[0].toUpperCase()}${tab.slice(1)}</div>`)
    .join("")}</nav>`;

  let body = "";
  if (input.tab === "overview") {
    body = `<div class="card" style="margin-top:16px">
      <div class="eyebrow">Program</div>
      <h1>Islamic Psychology Program</h1>
      <p>Nine courses · Terms 1–3 · one student host.</p>
      <div style="display:flex;gap:8px;margin:16px 0">
        <div class="card" style="flex:1;padding:12px"><div style="font-size:22px">${input.courses.length}</div><div class="muted">courses</div></div>
        <div class="card" style="flex:1;padding:12px"><div style="font-size:22px">${input.studentCount}</div><div class="muted">students</div></div>
        <div class="card" style="flex:1;padding:12px"><div style="font-size:22px">${input.pendingRequests}</div><div class="muted">requests</div></div>
      </div>
      <button class="btn btn-gold">Copy cmc.versed.page</button>
      <p class="muted" style="text-align:center;margin-top:10px">Access is by listed email or an approved request — not the link alone.</p>
    </div>`;
  } else if (input.tab === "content") {
    body = `<div class="card" style="margin-top:16px">
      <div class="eyebrow">Content</div>
      <h1>Nine ordinary courses</h1>
      <p class="muted">Open Manage course for materials. This page does not collapse them into one class.</p>
      ${input.courses
        .map(
          (course) => `<div class="row"><div><strong>${escapeHtml(course.code)}</strong><div class="muted">Term ${course.term} · ${escapeHtml(course.name)}</div></div><span class="chip">Manage course</span></div>`,
        )
        .join("")}
    </div>`;
  } else if (input.tab === "questions") {
    body =
      input.questions.length === 0
        ? `<div class="card empty" style="margin-top:16px"><div class="eyebrow">Questions</div><p>No class questions yet. Students can mark a passage as a question and optionally share it.</p></div>`
        : `<div class="card" style="margin-top:16px"><div class="eyebrow">Questions</div>${input.questions
            .map(
              (question) => `<div class="question">
                <div class="qmark" aria-hidden="true">?</div>
                <div>
                  <div class="qlabel">${QUESTION_LABEL}</div>
                  <div>${escapeHtml(question.selectedText || "")}</div>
                  <div class="muted">${question.visibility === "shared" ? "Shared with class" : "Just for them"} · ${question.status}</div>
                  ${question.answer ? `<p>${escapeHtml(question.answer)}</p>` : `<button class="btn btn-ghost" style="margin-top:8px">Answer</button>`}
                </div>
              </div>`,
            )
            .join("")}</div>`;
  } else {
    body = `<div class="card" style="margin-top:16px">
      <div class="eyebrow">Who can join</div>
      <h1>Allowed emails</h1>
      <p class="muted">${input.pendingRequests} pending request${input.pendingRequests === 1 ? "" : "s"}.</p>
      <textarea rows="4" placeholder="Paste emails, one per line"></textarea>
      <button class="btn btn-gold" style="margin-top:10px">Add emails</button>
      ${
        input.emails.length
          ? input.emails.map((email) => `<div class="row"><span>${escapeHtml(email)}</span><span class="chip">Remove</span></div>`).join("")
          : `<div class="empty">No emails yet. Until you add someone or approve a request, nobody new can enroll.</div>`
      }
    </div>`;
  }

  return shell("CMC teacher desk", `<div style="padding:16px">
    <div class="eyebrow">cmc.versed.page/admin</div>
    <h1 style="font-size:22px;margin-bottom:12px">Teacher desk</h1>
    ${tabBar}
    ${body}
  </div>`);
}

export function renderAdminLogin(surface: AdminSurface, state: ScreenState = "ready"): string {
  const copy = adminLoginCopy(surface);
  if (state === "loading") {
    return shell(copy.title, `<div style="padding:28px"><div class="spinner"></div><p class="muted" style="text-align:center">Checking your desk…</p></div>`);
  }
  return shell(copy.title, `<div style="padding:28px">
    <div class="eyebrow">${surface === "cmc-teacher" ? "Cambridge Muslim College" : "Versed"}</div>
    <h1>${escapeHtml(copy.title)}</h1>
    <p>${escapeHtml(copy.subtitle)}</p>
    <form style="display:grid;gap:10px;margin-top:18px">
      <input type="email" placeholder="Email" autocomplete="username" />
      <input type="password" placeholder="Password" autocomplete="current-password" />
      <button class="btn btn-primary" type="submit">${escapeHtml(copy.cta)}</button>
    </form>
    ${
      surface === "cmc-teacher"
        ? `<p class="muted" style="margin-top:18px">Students join at cmc.versed.page — this page is only for teachers. Super admin lives on versed.page/admin.</p>`
        : `<p class="muted" style="margin-top:18px">CMC teachers should use cmc.versed.page/admin, not this global desk.</p>`
    }
  </div>`);
}

export function renderHostJoin(input: {
  programName: string;
  gate: JoinGate;
  note?: string;
}): string {
  const title = input.programName;
  if (input.gate.status === "blocked") {
    return shell(title, `<div style="padding:28px">
      <div class="eyebrow">Islamic Psychology</div>
      <h1>${escapeHtml(title)}</h1>
      <p>Sign in with the email your teacher knows you by, then you can join or request access.</p>
      <button class="btn btn-primary">Sign in</button>
    </div>`);
  }
  if (input.gate.status === "enter") {
    return shell(title, `<div style="padding:28px">
      <div class="eyebrow">Program</div>
      <h1>${escapeHtml(title)}</h1>
      <p>${input.gate.reason === "already_enrolled" ? "You’re already in this program." : "Your email is on the list. Enter the nine-course library."}</p>
      <button class="btn btn-primary">${input.gate.reason === "already_enrolled" ? "Open program" : "Join program"}</button>
    </div>`);
  }
  if (input.gate.status === "pending") {
    return shell(title, `<div style="padding:28px">
      <div class="eyebrow">Request sent</div>
      <h1>Waiting for a teacher</h1>
      <p>Your request was sent. We’ll add you when it’s approved. You don’t need a join code.</p>
    </div>`);
  }
  if (input.gate.status === "denied") {
    return shell(title, `<div style="padding:28px">
      <div class="eyebrow">Not approved yet</div>
      <h1>Ask your teacher</h1>
      <p>This request wasn’t approved. Ask them to add your email on the teacher desk.</p>
    </div>`);
  }
  return shell(title, `<div style="padding:28px">
    <div class="eyebrow">Islamic Psychology</div>
    <h1>${escapeHtml(title)}</h1>
    <p>This program is for invited students. Request access and a teacher will approve you.</p>
    <textarea rows="3" placeholder="Optional note">${escapeHtml(input.note || "")}</textarea>
    <button class="btn btn-gold" style="margin-top:12px">Request access</button>
  </div>`);
}

export function renderQuestionChip(shared: boolean): string {
  const share = shared ? "Shared with class" : "Just for me";
  return `<span class="qlabel" style="color:${QUESTION_COLOR}">? ${QUESTION_LABEL}</span>
    <span class="chip">${share}</span>`;
}

export function renderStudentLibrary(input: {
  spaces: { id: string; label: string }[];
  activeSpaceId: string;
  programName: string | null;
  courseCount: number;
  personalUploadCount: number;
  showingUploads: boolean;
}): string {
  const switcher =
    input.spaces.length > 1
      ? `<div class="tabs" role="tablist" aria-label="Space">${input.spaces
          .map(
            (space) =>
              `<button class="tab ${space.id === input.activeSpaceId ? "active" : ""}" type="button">${escapeHtml(space.label)}</button>`,
          )
          .join("")}</div>`
      : "";
  const program = input.programName
    ? `<div class="card" style="margin-top:16px">
        <div class="eyebrow">Program</div>
        <h1 style="font-size:22px">${escapeHtml(input.programName)}</h1>
        <p class="muted">${input.courseCount} courses · Terms 1–3 · C1 / C2 / C3</p>
      </div>`
    : `<div class="card empty" style="margin-top:16px"><p>No program in this space yet.</p></div>`;
  const uploads = input.showingUploads
    ? `<div class="card" style="margin-top:12px"><div class="eyebrow">Your uploads</div><p>${input.personalUploadCount} personal text${input.personalUploadCount === 1 ? "" : "s"}.</p></div>`
    : `<p class="muted" style="margin-top:12px">Personal uploads live in My library — class readings stay here.</p>`;
  return shell("Library", `<div style="padding:16px">
    <div class="eyebrow">Space</div>
    <h1 style="font-size:22px;margin-bottom:12px">Your library</h1>
    ${switcher}
    ${program}
    ${uploads}
  </div>`);
}
