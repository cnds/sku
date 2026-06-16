import type { CSSProperties } from "react";

const PAGE_BOTTOM_SPACER_STYLE: CSSProperties = {
  height: "3rem",
};

export function PageBottomSpacer() {
  return <div aria-hidden="true" style={PAGE_BOTTOM_SPACER_STYLE} />;
}
