import {
  Badge,
  Box,
  Card,
  EmptyState,
  IndexTable,
  InlineStack,
  Text,
} from "@shopify/polaris";
import type { LeaderboardEntry, TimeWindow } from "@/lib/contracts";
import { messages } from "@/lib/messages";
import { productPath } from "@/lib/url";

interface LeaderboardTableProps {
  rows: LeaderboardEntry[];
  shopId: string;
  title: string;
  subtitle: string;
  tone: "critical" | "success";
  window: TimeWindow;
}

export function LeaderboardTable({
  rows,
  shopId,
  title,
  subtitle,
  tone,
  window,
}: LeaderboardTableProps) {
  if (rows.length === 0) {
    return (
      <Card>
        <EmptyState
          heading={messages.leaderboard.emptyHeading(title)}
          image="https://cdn.shopify.com/s/files/1/0262/4071/2726/files/emptystate-files.png"
        >
          <Text as="p" variant="bodyMd" tone="subdued">
            {messages.leaderboard.emptyDescription}
          </Text>
        </EmptyState>
      </Card>
    );
  }

  const resourceName = { singular: messages.leaderboard.resourceSingular, plural: messages.leaderboard.resourcePlural };

  return (
    <Card padding="0">
      <Box paddingInline="400" paddingBlockStart="400" paddingBlockEnd="200">
        <InlineStack align="space-between" blockAlign="center">
          <InlineStack gap="200" blockAlign="center">
            <Text as="h2" variant="headingMd">
              {title}
            </Text>
            <Badge tone={tone === "critical" ? "critical" : "success"}>
              {messages.leaderboard.productCount(rows.length)}
            </Badge>
          </InlineStack>
        </InlineStack>
        <Box paddingBlockStart="100">
          <Text as="p" variant="bodySm" tone="subdued">
            {subtitle}
          </Text>
        </Box>
      </Box>
      <IndexTable
        resourceName={resourceName}
        itemCount={rows.length}
        headings={[
          { title: messages.leaderboard.columnRank },
          { title: messages.leaderboard.columnProduct },
          { title: messages.leaderboard.columnScore, alignment: "end" },
        ]}
        selectable={false}
      >
        {rows.map((row, index) => (
          <IndexTable.Row
            id={row.product_id}
            key={row.product_id}
            position={index}
          >
            <IndexTable.Cell>
              <Text as="span" variant="bodyMd" fontWeight="bold" tone={tone === "critical" ? "critical" : "success"}>
                {index + 1}
              </Text>
            </IndexTable.Cell>
            <IndexTable.Cell>
              <Text as="span" variant="bodyMd" fontWeight="semibold">
                <a
                  href={productPath(row.product_id, shopId, window)}
                  style={{ color: "var(--p-color-text-link)", textDecoration: "none" }}
                >
                  {row.product_id}
                </a>
              </Text>
            </IndexTable.Cell>
            <IndexTable.Cell>
              <InlineStack align="end">
                <Badge tone={tone}>
                  {row.score.toFixed(1)}
                </Badge>
              </InlineStack>
            </IndexTable.Cell>
          </IndexTable.Row>
        ))}
      </IndexTable>
    </Card>
  );
}
