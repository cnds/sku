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
import interactiveStyles from "@/styles/interactive.module.css";

type ActivityRow = Pick<LeaderboardEntry, "add_to_carts" | "orders" | "views">;

interface LeaderboardTableProps {
  host?: string;
  rows: LeaderboardEntry[];
  shopId: string;
  title: string;
  subtitle: string;
  tone: "critical" | "success";
  window: TimeWindow;
}

function formatCount(value: number, singular: string, plural: string): string {
  return `${value.toLocaleString("en-US")} ${value === 1 ? singular : plural}`;
}

export function formatLeaderboardActivity(row: ActivityRow): string {
  return [
    formatCount(row.views, "view", "views"),
    formatCount(row.add_to_carts, "cart", "carts"),
    formatCount(row.orders, "order", "orders"),
  ].join(" · ");
}

export function LeaderboardTable({
  host,
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
          { title: messages.leaderboard.columnProduct },
          { title: messages.leaderboard.columnSignal },
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
              <Text as="span" variant="bodyMd" fontWeight="semibold">
                <a
                  className={interactiveStyles.tableLink}
                  href={productPath(row.product_id, shopId, window, host)}
                >
                  {row.product_id}
                </a>
              </Text>
            </IndexTable.Cell>
            <IndexTable.Cell>
              <Text as="span" variant="bodySm" tone="subdued">
                {formatLeaderboardActivity(row)}
              </Text>
            </IndexTable.Cell>
          </IndexTable.Row>
        ))}
      </IndexTable>
    </Card>
  );
}
