export const colors = {
  canvas: "#F4EFE6",
  primary: "#FBF7F0",
  secondary: "#F2E9DC",
  elevated: "#FFFDFC",
  inverse: "#1F1A17",
  text: "#201A16",
  textSecondary: "#5C4D40",
  muted: "#A48C74",
  gold: "#B7793E",
  goldSoft: "#E8C7A2",
  amber: "#D28A2D",
  error: "#C85D4B",
  success: "#4D8B5B",
  border: "#E6DACA",
  panel: "#F7F0E5",
} as const;

export type ScreenState = "loading" | "empty" | "ready" | "error";
