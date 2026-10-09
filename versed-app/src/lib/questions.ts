export type CommentKind = "highlight" | "question";
export type CommentVisibility = "private" | "shared";
export type CommentStatus = "open" | "answered" | "closed";

export type BookComment = {
  id: string;
  userId: string;
  kind: CommentKind;
  visibility: CommentVisibility;
  status: CommentStatus;
  page: number | null;
  block: string | null;
  word: string | null;
  selectedText: string | null;
  color: string | null;
  body?: string | null;
  answer?: string | null;
};

export const QUESTION_COLOR = "#D28A2D";
export const QUESTION_LABEL = "Question";

export function questionPresentation(comment: Pick<BookComment, "kind" | "color">): {
  label: string;
  color: string;
  icon: "question";
} | null {
  if (comment.kind !== "question") return null;
  return {
    label: QUESTION_LABEL,
    color: comment.color || QUESTION_COLOR,
    icon: "question",
  };
}

export function isVisibleToClass(comment: BookComment, viewerId: string, sharedEnabled: boolean): boolean {
  if (comment.userId === viewerId) return true;
  if (comment.visibility !== "shared") return false;
  if (comment.kind === "question") return sharedEnabled;
  return sharedEnabled;
}

export function createQuestionDraft(input: {
  userId: string;
  selectedText: string;
  page?: number | null;
  block?: string | null;
  word?: string | null;
  shareWithClass: boolean;
}): Omit<BookComment, "id"> {
  return {
    userId: input.userId,
    kind: "question",
    visibility: input.shareWithClass ? "shared" : "private",
    status: "open",
    page: input.page ?? null,
    block: input.block ?? null,
    word: input.word ?? null,
    selectedText: input.selectedText,
    color: QUESTION_COLOR,
  };
}

export function answerQuestion(comment: BookComment, answer: string): BookComment {
  return { ...comment, answer, status: "answered" };
}
