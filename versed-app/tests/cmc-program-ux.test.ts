import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeEmail, parseEmailList } from "../src/lib/emails.ts";
import { canEnrollInProgram } from "../src/lib/programAccess.ts";
import { isCmcHost, resolveProgramFromHost } from "../src/lib/host.ts";
import { COURSE_MATERIAL_LIBRARY_SELECT, groupReadingsByWeek, mapCourseMaterial } from "../src/lib/groupReadings.ts";
import { sharedAnnotationsEnabled } from "../src/lib/sharedAnnotations.ts";
import { answerQuestion, createQuestionDraft, isVisibleToClass, questionPresentation } from "../src/lib/questions.ts";
import { canOpenCmcTeacherDesk, resolveAdminSurface } from "../src/lib/adminAccess.ts";
import { decideProgramJoin, enrollWithoutOrgMembership } from "../src/server/joinProgram.ts";
import { defaultSpaceId, filterLibraryForSpace, LIBRARY_SPACE, spacesForStudent } from "../src/lib/spaces.ts";
import { renderAdminLogin, renderCmcTeacherAdmin, renderHostJoin, renderStudentLibrary, renderStudentReadingList } from "../src/ui/render.ts";

test("normalizeEmail lowercases and rejects junk", () => {
  assert.equal(normalizeEmail("  Sara@CMC.Example "), "sara@cmc.example");
  assert.equal(normalizeEmail("not-an-email"), null);
});

test("parseEmailList pastes, skips dupes, reports invalid", () => {
  const parsed = parseEmailList("sara@cmc.example\nsara@cmc.example, nope\nyusuf@cmc.example");
  assert.deepEqual(parsed.emails, ["sara@cmc.example", "yusuf@cmc.example"]);
  assert.deepEqual(parsed.invalid, ["nope"]);
});

test("join code is not enough: empty allowlist cannot enroll", async () => {
  const decision = await decideProgramJoin({
    hostname: "cmc.versed.page",
    email: "stranger@example.com",
    allowlist: [],
    alreadyEnrolled: false,
    joinCode: "SECRET",
  });
  assert.equal(decision.ok, false);
  if (!decision.ok) assert.equal(decision.gate.status, "request");
});

test("allowlisted email may enter; enroll does not create org membership", async () => {
  const decision = await decideProgramJoin({
    hostname: "cmc.versed.page",
    email: "sara@cmc.example",
    allowlist: ["sara@cmc.example"],
    alreadyEnrolled: false,
  });
  assert.equal(decision.ok, true);
  const row = enrollWithoutOrgMembership({
    userId: "u1",
    programId: "p1",
    email: "sara@cmc.example",
  });
  assert.equal(row.orgMember, false);
});

test("pending and denied request states", () => {
  assert.equal(
    canEnrollInProgram({
      email: "sara@cmc.example",
      allowlist: [],
      alreadyEnrolled: false,
      requestStatus: "pending",
    }).status,
    "pending",
  );
  assert.equal(
    canEnrollInProgram({
      email: "sara@cmc.example",
      allowlist: [],
      alreadyEnrolled: false,
      requestStatus: "denied",
    }).status,
    "denied",
  );
});

test("cmc.versed.page maps to the Islamic Psychology program", () => {
  assert.equal(isCmcHost("cmc.versed.page"), true);
  assert.equal(resolveProgramFromHost("www.cmc.versed.page")?.code, "ISLAMIC-PSYCHOLOGY");
  assert.equal(resolveProgramFromHost("www.versed.page"), null);
});

test("spaces: class readings are not locked to cmc.versed.page", () => {
  const spaces = spacesForStudent({ enrolledInCmc: true });
  assert.deepEqual(spaces.map((space) => space.id), ["cmc-program", "library"]);

  assert.equal(defaultSpaceId({ hostname: "cmc.versed.page", enrolledInCmc: true }), "cmc-program");
  assert.equal(defaultSpaceId({ hostname: "www.versed.page", enrolledInCmc: true }), "library");
  assert.equal(
    defaultSpaceId({ hostname: "www.versed.page", preferred: "cmc-program", enrolledInCmc: true }),
    "cmc-program",
  );

  const program = [{ id: "islamic-psychology" }];
  const uploads = [{ id: "my-pdf" }];
  const onVersed = filterLibraryForSpace({
    space: spaces.find((space) => space.id === "library") ?? LIBRARY_SPACE,
    programs: program,
    personalUploads: uploads,
  });
  assert.equal(onVersed.programs.length, 1);
  assert.equal(onVersed.personalUploads.length, 1);

  const onCmc = filterLibraryForSpace({
    space: spaces[0]!,
    programs: program,
    personalUploads: uploads,
  });
  assert.equal(onCmc.programs.length, 1);
  assert.equal(onCmc.personalUploads.length, 0);
});

test("library select includes week_number and is_required", () => {
  assert.match(COURSE_MATERIAL_LIBRARY_SELECT, /week_number/);
  assert.match(COURSE_MATERIAL_LIBRARY_SELECT, /is_required/);
  const mapped = mapCourseMaterial({
    id: "m1",
    course_id: "c1",
    book_id: "b1",
    title_override: null,
    week_number: 3,
    sequence_order: 2,
    is_required: false,
    books: { id: "b1", title: "Essay", author: "Staff", status: "ready" },
  });
  assert.equal(mapped.weekNumber, 3);
  assert.equal(mapped.isRequired, false);
  const weeks = groupReadingsByWeek([
    { ...mapped, title: "Optional essay", sequenceOrder: 2 },
    {
      id: "m0",
      courseId: "c1",
      bookId: "b0",
      title: "Required root text",
      author: null,
      weekNumber: 3,
      sequenceOrder: 1,
      isRequired: true,
    },
  ]);
  assert.equal(weeks[0]?.label, "Week 3");
  assert.equal(weeks[0]?.required[0]?.title, "Required root text");
  assert.equal(weeks[0]?.optional[0]?.title, "Optional essay");
});

test("shared annotations cascade course → program → org → false", () => {
  assert.equal(sharedAnnotationsEnabled({}), false);
  assert.equal(sharedAnnotationsEnabled({ org: true }), true);
  assert.equal(sharedAnnotationsEnabled({ org: true, program: false }), false);
  assert.equal(sharedAnnotationsEnabled({ org: false, program: false, course: true }), true);
});

test("questions are labelled and optionally shared; private stays private", () => {
  const shared = { ...createQuestionDraft({ userId: "s1", selectedText: "Why?", shareWithClass: true }), id: "1" };
  const priv = { ...createQuestionDraft({ userId: "s1", selectedText: "Secret", shareWithClass: false }), id: "2" };
  const mark = questionPresentation(shared);
  assert.equal(mark?.label, "Question");
  assert.equal(mark?.icon, "question");
  assert.equal(isVisibleToClass(priv, "teacher", true), false);
  assert.equal(isVisibleToClass(shared, "teacher", true), true);
  assert.equal(isVisibleToClass(shared, "teacher", false), false);
  assert.equal(isVisibleToClass(priv, "s1", false), true);
  assert.equal(answerQuestion(shared, "Because.").status, "answered");
});

test("cmc.versed.page/admin is the teacher desk, not super admin", () => {
  const teacher = { email: "teacher@cmc.example", isSuperAdmin: false, isCmcTeacher: true };
  const student = { email: "student@cmc.example", isSuperAdmin: false, isCmcTeacher: false };
  const bilal = { email: "bg@bilalghalib.com", isSuperAdmin: true, isCmcTeacher: false };

  assert.equal(
    resolveAdminSurface({ hostname: "cmc.versed.page", pathname: "/admin", identity: teacher }),
    "cmc-teacher",
  );
  assert.equal(
    resolveAdminSurface({ hostname: "www.versed.page", pathname: "/admin", identity: teacher }),
    "none",
  );
  assert.equal(
    resolveAdminSurface({ hostname: "www.versed.page", pathname: "/admin", identity: bilal }),
    "super-admin",
  );
  assert.equal(
    resolveAdminSurface({ hostname: "cmc.versed.page", pathname: "/sourced-super-admin", identity: teacher }),
    "none",
  );
  assert.equal(
    resolveAdminSurface({ hostname: "cmc.versed.page", pathname: "/sourced-super-admin", identity: bilal }),
    "super-admin",
  );
  assert.equal(canOpenCmcTeacherDesk(teacher), true);
  assert.equal(canOpenCmcTeacherDesk(student), false);
  assert.equal(canOpenCmcTeacherDesk(bilal), true);
});

test("student and teacher screens have intentional empty and loading states", () => {
  const loading = renderStudentReadingList({
    programName: "Islamic Psychology Program",
    term: 1,
    componentCode: "C1",
    courseName: "Historical foundations",
    state: "loading",
  });
  assert.match(loading, /Loading this course/);
  const empty = renderStudentReadingList({
    programName: "Islamic Psychology Program",
    term: 1,
    componentCode: "C2",
    courseName: "Theological perspectives",
    state: "empty",
  });
  assert.match(empty, /No readings yet/);
  const ready = renderStudentReadingList({
    programName: "Islamic Psychology Program",
    term: 1,
    componentCode: "C1",
    courseName: "Historical foundations",
    state: "ready",
    weeks: groupReadingsByWeek([
      {
        id: "1",
        courseId: "c1",
        bookId: "b1",
        title: "Root text",
        author: null,
        weekNumber: 1,
        sequenceOrder: 1,
        isRequired: true,
      },
    ]),
  });
  assert.match(ready, /Week 1/);
  assert.match(ready, /Required/);

  const settings = renderCmcTeacherAdmin({
    tab: "settings",
    studentCount: 0,
    pendingRequests: 0,
    emails: [],
    questions: [],
    courses: [{ code: "C1", name: "Historical foundations", term: 1 }],
  });
  assert.match(settings, /No emails yet/);
  assert.match(settings, /Overview|Content|Questions|Settings/i);
  const content = renderCmcTeacherAdmin({
    tab: "content",
    studentCount: 0,
    pendingRequests: 0,
    emails: [],
    questions: [],
    courses: [{ code: "C1", name: "Historical foundations", term: 1 }],
  });
  assert.match(content, /Manage course/);

  const login = renderAdminLogin("cmc-teacher");
  assert.match(login, /CMC teacher desk/);
  assert.match(login, /versed\.page\/admin/);
  assert.match(renderHostJoin({
    programName: "Islamic Psychology Program",
    gate: { status: "request", reason: "not_allowlisted" },
  }), /Request access/);

  const library = renderStudentLibrary({
    spaces: [
      { id: "cmc-program", label: "Islamic Psychology Program" },
      { id: "library", label: "My library" },
    ],
    activeSpaceId: "library",
    programName: "Islamic Psychology Program",
    courseCount: 9,
    personalUploadCount: 2,
    showingUploads: true,
  });
  assert.match(library, /My library/);
  assert.match(library, /Your uploads/);
  assert.match(library, /Islamic Psychology Program/);
});
