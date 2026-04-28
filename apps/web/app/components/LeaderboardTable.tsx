import {
  Badge,
  Box,
  Card,
  EmptyState,
  IndexTable,
  InlineStack,
  Text,
  useBreakpoints,
} from "@shopify/polaris";
import type { LeaderboardEntry, TimeWindow } from "@/lib/contracts";
import { messages } from "@/lib/messages";
import { productPath } from "@/lib/url";

interface LeaderboardTableProps {
  rows: LeaderboardEntry[];
  shopId: string;
  title: string;
  tone: "critical" | "success";
  window: TimeWindow;
}

function scoreTone(score: number, boardTone: "critical" | "success"): "attention" | "critical" | "success" | "info" {
  if (boardTone === "critical") {
    return score >= 50 ? "critical" : "attention";
  }
  return score >= 50 ? "success" : "info";
}

export function LeaderboardTable({
  rows,
  shopId,
  title,
  tone,
  window,
}: LeaderboardTableProps) {
  const { smUp } = useBreakpoints();

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
      </Box>
      <IndexTable
        resourceName={resourceName}
        itemCount={rows.length}
        headings={[
          { title: messages.leaderboard.columnRank },
          { title: messages.leaderboard.columnProduct },
          { title: messages.leaderboard.columnViews, alignment: "end" },
          { title: messages.leaderboard.columnAddToCart, alignment: "end" },
          { title: messages.leaderboard.columnOrders, alignment: "end" },
          { title: messages.leaderboard.columnScore, alignment: "end" },
        ]}
        selectable={false}
        condensed={!smUp}
      >
        {rows.map((row, index) => (
          <IndexTable.Row
            id={row.product_id}
            key={row.product_id}
            position={index}
          >
            <IndexTable.Cell>
              <Text as="span" variant="bodyMd" tone="subdued">
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
              <Text as="span" variant="bodyMd" alignment="end">
                {row.views.toLocaleString()}
              </Text>
            </IndexTable.Cell>
            <IndexTable.Cell>
              <Text as="span" variant="bodyMd" alignment="end">
                {row.add_to_carts.toLocaleString()}
              </Text>
            </IndexTable.Cell>
            <IndexTable.Cell>
              <Text as="span" variant="bodyMd" alignment="end">
                {row.orders.toLocaleString()}
              </Text>
            </IndexTable.Cell>
            <IndexTable.Cell>
              <InlineStack align="end">
                <Badge tone={scoreTone(row.score, tone)}>
                  {row.score.toFixed(2)}
                </Badge>
              </InlineStack>
            </IndexTable.Cell>
          </IndexTable.Row>
        ))}
      </IndexTable>
    </Card>
  );
}
