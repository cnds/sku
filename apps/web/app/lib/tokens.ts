import type { CSSProperties } from "react";

// Shared visual tokens aligned to the Polaris design system.
// Use these instead of scattering raw values across route and component files.

/** Outer card containers (priority section, priority card wrapper). */
export const CARD_BORDER_RADIUS = "var(--p-border-radius-300, 12px)";

/** Inner containers (metrics strip, action box, journey step, diagnosis card). */
export const INNER_BORDER_RADIUS = "var(--p-border-radius-200, 8px)";

/** Standard card elevation. */
export const CARD_SHADOW = "var(--p-shadow-200, 0 2px 8px rgba(0, 0, 0, 0.06))";

/** Secondary border — no fallback needed on Polaris 13+. */
export const BORDER_SECONDARY = "var(--p-color-border-secondary)";

/** Divider style reused for feedback / why-now separators. */
export const DIVIDER_STYLE: CSSProperties = {
  borderTop: `1px solid ${BORDER_SECONDARY}`,
  paddingTop: "0.75rem",
};
