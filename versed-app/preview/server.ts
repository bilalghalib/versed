import { createServer } from "node:http";
import { groupReadingsByWeek, type LibraryMaterial } from "../src/lib/groupReadings.ts";
import { canEnrollInProgram } from "../src/lib/programAccess.ts";
import { answerQuestion, createQuestionDraft } from "../src/lib/questions.ts";
import {
  renderAdminLogin,
  renderCmcTeacherAdmin,
  renderHostJoin,
  renderStudentLibrary,
  renderStudentReadingList,
} from "../src/ui/render.ts";
import { filterLibraryForSpace, spacesForStudent } from "../src/lib/spaces.ts";

const readings: LibraryMaterial[] = [
  {
    id: "1",
    courseId: "c1",
    bookId: "b1",
    title: "Ihya — Book of Knowledge",
    author: "al-Ghazali",
    weekNumber: 1,
    sequenceOrder: 1,
    isRequired: true,
  },
  {
    id: "2",
    courseId: "c1",
    bookId: "b2",
    title: "Optional companion essay",
    author: "Staff",
    weekNumber: 1,
    sequenceOrder: 2,
    isRequired: false,
  },
  {
    id: "3",
    courseId: "c1",
    bookId: "b3",
    title: "Term overview lecture notes",
    author: null,
    weekNumber: 2,
    sequenceOrder: 1,
    isRequired: true,
  },
];

const asked = createQuestionDraft({
  userId: "student-1",
  selectedText: "What does nafs mean in this passage?",
  page: 12,
  shareWithClass: true,
});
const questions = [
  { ...asked, id: "q1" },
  {
    ...answerQuestion({ ...asked, id: "q2" }, "Nafs here is the struggling self — see week 2."),
    selectedText: "How should we read qalb?",
  },
];

const courses = [
  { code: "C1", name: "Historical foundations", term: 1 },
  { code: "C2", name: "Theological perspectives", term: 1 },
  { code: "C3", name: "Medical and social", term: 1 },
];

const studentSpaces = spacesForStudent({ enrolledInCmc: true });
const cmcView = filterLibraryForSpace({
  space: studentSpaces[0]!,
  programs: [{ name: "Islamic Psychology Program" }],
  personalUploads: [{ title: "My notes PDF" }],
});
const libraryView = filterLibraryForSpace({
  space: studentSpaces[1]!,
  programs: [{ name: "Islamic Psychology Program" }],
  personalUploads: [{ title: "My notes PDF" }],
});

const pages: Record<string, string> = {
  "/": `<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><body style="font-family:serif;background:#F4EFE6;padding:24px">
    <h1>CMC UX preview</h1>
    <ul>
      <li><a href="/student-readings">Student week list</a></li>
      <li><a href="/student-empty">Student empty readings</a></li>
      <li><a href="/student-loading">Student loading</a></li>
      <li><a href="/space-cmc">Space: Islamic Psychology</a></li>
      <li><a href="/space-library">Space: My library (class + uploads)</a></li>
      <li><a href="/join">Host join / request</a></li>
      <li><a href="/join-pending">Host join pending</a></li>
      <li><a href="/admin-login">CMC /admin login</a></li>
      <li><a href="/super-admin-login">Versed super admin login</a></li>
      <li><a href="/teacher">Teacher overview</a></li>
      <li><a href="/teacher-settings">Teacher settings</a></li>
      <li><a href="/teacher-questions">Teacher questions</a></li>
    </ul>
  </body>`,
  "/student-readings": renderStudentReadingList({
    programName: "Islamic Psychology Program",
    term: 1,
    componentCode: "C1",
    courseName: "Historical foundations",
    state: "ready",
    weeks: groupReadingsByWeek(readings),
  }),
  "/student-empty": renderStudentReadingList({
    programName: "Islamic Psychology Program",
    term: 2,
    componentCode: "C2",
    courseName: "Theological perspectives",
    state: "empty",
  }),
  "/student-loading": renderStudentReadingList({
    programName: "Islamic Psychology Program",
    term: 1,
    componentCode: "C3",
    courseName: "Medical and social",
    state: "loading",
  }),
  "/space-cmc": renderStudentLibrary({
    spaces: studentSpaces,
    activeSpaceId: "cmc-program",
    programName: cmcView.programs[0]?.name ?? null,
    courseCount: 9,
    personalUploadCount: cmcView.personalUploads.length,
    showingUploads: false,
  }),
  "/space-library": renderStudentLibrary({
    spaces: studentSpaces,
    activeSpaceId: "library",
    programName: libraryView.programs[0]?.name ?? null,
    courseCount: 9,
    personalUploadCount: libraryView.personalUploads.length,
    showingUploads: true,
  }),
  "/join": renderHostJoin({
    programName: "Islamic Psychology Program",
    gate: canEnrollInProgram({ email: "student@example.com", allowlist: [], alreadyEnrolled: false }),
  }),
  "/join-pending": renderHostJoin({
    programName: "Islamic Psychology Program",
    gate: canEnrollInProgram({
      email: "student@example.com",
      allowlist: [],
      alreadyEnrolled: false,
      requestStatus: "pending",
    }),
  }),
  "/admin-login": renderAdminLogin("cmc-teacher"),
  "/super-admin-login": renderAdminLogin("super-admin"),
  "/teacher": renderCmcTeacherAdmin({
    tab: "overview",
    studentCount: 0,
    pendingRequests: 2,
    emails: [],
    questions,
    courses,
  }),
  "/teacher-settings": renderCmcTeacherAdmin({
    tab: "settings",
    studentCount: 12,
    pendingRequests: 2,
    emails: ["sara@cmc.example", "yusuf@cmc.example"],
    questions,
    courses,
  }),
  "/teacher-questions": renderCmcTeacherAdmin({
    tab: "questions",
    studentCount: 12,
    pendingRequests: 0,
    emails: ["sara@cmc.example"],
    questions,
    courses,
  }),
};

const server = createServer((req, res) => {
  const url = new URL(req.url || "/", "http://127.0.0.1");
  const html = pages[url.pathname];
  if (!html) {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end("Not found");
    return;
  }
  res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  res.end(html);
});

const port = Number(process.env.PORT || 4173);
server.listen(port, "127.0.0.1", () => {
  console.log(`CMC preview http://127.0.0.1:${port}/`);
});
