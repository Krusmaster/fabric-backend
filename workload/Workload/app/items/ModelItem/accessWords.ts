// n213: the one quiet line about the organisation's trial or subscription (fabric_backend/billing.py words it).
import type { AccessAnswer } from "./engineClient";

/** The line to show, or "" for none: the switch off, an exempt or subscribed organisation within its plan, or no answer. */
export function accessLine(answer: AccessAnswer | null | undefined): string {
  if (!answer || typeof answer.words !== "string") return "";
  return answer.words.trim().slice(0, 400);
}
