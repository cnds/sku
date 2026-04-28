import type { LeaderboardEntry, TimeWindow } from "@/lib/contracts";
import { messages } from "@/lib/messages";

export const TIME_WINDOWS: Array<{ label: string; value: TimeWindow }> = [
  { label: messages.timeWindows["24h"], value: "24h" },
  { label: messages.timeWindows["7d"], value: "7d" },
  { label: messages.timeWindows["30d"], value: "30d" },
];

export const COMPONENT_LABELS: Record<string, string> = messages.componentLabels;

export function calculateGap(
  productViews: number,
  storeAverageConversionRate: number,
  actualOrders: number,
): number {
  return productViews * storeAverageConversionRate - actualOrders;
}

export function calculateRedBoardOpportunity(
  entry: LeaderboardEntry,
  storeAverageViews: number,
): number {
  if (entry.views === 0) {
    return 0;
  }

  return (entry.add_to_carts / entry.views) * storeAverageViews - entry.views;
}

export function formatTimeWindowLabel(window: TimeWindow): string {
  const match = TIME_WINDOWS.find((option) => option.value === window);
  return match?.label ?? window;
}
