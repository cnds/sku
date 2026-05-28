import type { PriorityCard, PrioritySignalState, PriorityTrendState } from "@/lib/contracts";
import { messages } from "@/lib/messages";

export type PriorityBadgeTone = "attention" | "critical" | "info" | "success";

export function priorityBoardLabel(board: PriorityCard["board"]): string {
  return board === "hidden_winner" ? "Hidden Winner" : messages.dashboard.blackboardTitle;
}

const PRIORITY_STEP_LABELS: Record<string, string> = {
  cart_to_order: "Drop-off: add-to-cart to order",
  collection_click: "Drop-off: collection impression to click",
  data_volume: "Signal: data volume",
  merchandising_reach: "Opportunity: merchandising reach",
  pdp_add_to_cart: "Drop-off: PDP view to add-to-cart",
  pdp_decision: "Drop-off: PDP decision",
  tracking_coverage: "Tracking: event coverage",
};

export function priorityStepLabel(step: string): string {
  return PRIORITY_STEP_LABELS[step] ?? `Signal: ${step.replaceAll("_", " ")}`;
}

export function priorityTone(card: Pick<PriorityCard, "board" | "signal_state">): PriorityBadgeTone {
  if (card.signal_state === "Tracking issue") return "attention";
  if (card.signal_state === "Insufficient data" || card.signal_state === "Weak signal") return "info";
  return card.board === "hidden_winner" ? "success" : "critical";
}

export function priorityActionLabel(card: Pick<PriorityCard, "board" | "card_rank">): string {
  if (card.board === "hidden_winner") return "Scale carefully";
  return card.card_rank === 1 ? "Fix first" : "Fix next";
}

export function priorityTrendTone(
  trend: PriorityTrendState,
): "critical" | "info" | "success" | undefined {
  if (trend === "Worsening") return "critical";
  if (trend === "Improving") return "success";
  if (trend === "New") return "info";
  return undefined;
}

export function prioritySignalTone(
  signalState: PrioritySignalState,
): "attention" | "info" | undefined {
  if (signalState === "Tracking issue") return "attention";
  if (signalState === "Insufficient data" || signalState === "Weak signal") return "info";
  return undefined;
}

export function priorityAccentColor(card: Pick<PriorityCard, "board">): string {
  return card.board === "hidden_winner"
    ? "var(--p-color-border-success, #008060)"
    : "var(--p-color-border-critical, #d82c0d)";
}

export function priorityActionBackground(card: Pick<PriorityCard, "board">): string {
  return card.board === "hidden_winner"
    ? "rgba(0, 128, 96, 0.05)"
    : "rgba(216, 44, 13, 0.05)";
}
