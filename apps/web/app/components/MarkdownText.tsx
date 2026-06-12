import type { CSSProperties, ReactNode } from "react";
import { BlockStack } from "@shopify/polaris";

const PARAGRAPH_STYLE: CSSProperties = {
  margin: 0,
};

const LIST_STYLE: CSSProperties = {
  margin: 0,
  paddingLeft: "1.15rem",
};

export function MarkdownText({ fallback, markdown }: { fallback: string; markdown: string }) {
  const content = markdown.trim();
  if (!content) {
    return <>{fallback}</>;
  }

  const blocks = content.split(/\n{2,}/).filter((block) => block.trim());
  return (
    <BlockStack gap="200">
      {blocks.map((block, blockIndex) => {
        const lines = block.split(/\n/).map((line) => line.trim()).filter(Boolean);
        const isList = lines.length > 0 && lines.every((line) => /^[-*]\s+/.test(line));
        if (isList) {
          return (
            <ul key={`block-${blockIndex}`} style={LIST_STYLE}>
              {lines.map((line, lineIndex) => (
                <li key={`line-${lineIndex}`}>
                  {renderInlineMarkdown(line.replace(/^[-*]\s+/, ""), `${blockIndex}-${lineIndex}`)}
                </li>
              ))}
            </ul>
          );
        }

        return (
          <p key={`block-${blockIndex}`} style={PARAGRAPH_STYLE}>
            {lines.map((line, lineIndex) => (
              <span key={`line-${lineIndex}`}>
                {lineIndex > 0 ? <br /> : null}
                {renderInlineMarkdown(line, `${blockIndex}-${lineIndex}`)}
              </span>
            ))}
          </p>
        );
      })}
    </BlockStack>
  );
}

function renderInlineMarkdown(value: string, keyPrefix: string): ReactNode[] {
  return value.split(/(\*\*[^*]+?\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${keyPrefix}-${index}`}>{part.slice(2, -2)}</strong>;
    }

    return part;
  });
}
