import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const interactiveStyles = readFileSync(
  new URL("../app/styles/interactive.module.css", import.meta.url),
  "utf8",
);

function cssRuleBlock(selector: string): string {
  const match = interactiveStyles.match(new RegExp(`${selector.replace(".", "\\.")}\\s*\\{([^}]*)\\}`));
  expect(match).not.toBeNull();
  return match?.[1] ?? "";
}

describe("interactive styles", () => {
  it("uses a supported Polaris text token for inactive time window options", () => {
    const ruleBlock = cssRuleBlock(".timeWindowOption");

    expect(ruleBlock).toContain("color: var(--p-color-text-secondary);");
    expect(ruleBlock).not.toContain("--p-color-text-subdued");
  });
});
