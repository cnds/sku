import type { TimeWindow } from "@/lib/contracts";
import { messages } from "@/lib/messages";

export const TIME_WINDOWS: Array<{ label: string; value: TimeWindow }> = [
  { label: messages.timeWindows["24h"], value: "24h" },
  { label: messages.timeWindows["7d"], value: "7d" },
  { label: messages.timeWindows["30d"], value: "30d" },
];

export function formatTimeWindowLabel(window: TimeWindow): string {
  const match = TIME_WINDOWS.find((option) => option.value === window);
  return match?.label ?? window;
}
