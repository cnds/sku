import { useCallback, useMemo } from "react";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { isRouteErrorResponse, useLoaderData, useNavigate, useRouteError } from "@remix-run/react";
import {
  Badge,
  Banner,
  BlockStack,
  Box,
  Card,
  InlineGrid,
  InlineStack,
  Layout,
  Page,
  Tabs,
  Text,
} from "@shopify/polaris";

import { LeaderboardTable } from "@/components/LeaderboardTable";
import { TIME_WINDOWS, formatTimeWindowLabel } from "@/lib/analytics";
import { fetchLeaderboard, fetchPriorities, parseTimeWindow } from "@/lib/api.server";
import type { PriorityCard } from "@/lib/contracts";
import { requestIdFromHeaders } from "@/lib/logging";
import { messages } from "@/lib/messages";
import { dashboardPath, productPath } from "@/lib/url";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const requestId = requestIdFromHeaders(request.headers);
  const shopId = url.searchParams.get("shop") ?? "demo.myshopify.com";
  const window = parseTimeWindow(url.searchParams.get("window"));
  const [priorities, blackboard, redboard] = await Promise.all([
    fetchPriorities({ requestId, shopId, window }),
    fetchLeaderboard({ board: "black", requestId, shopId, window }),
    fetchLeaderboard({ board: "red", requestId, shopId, window }),
  ]);

  return { blackboard, priorities, redboard, shopId, window };
}

function priorityBoardLabel(board: PriorityCard["board"]): string {
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

function priorityTone(card: PriorityCard): "attention" | "critical" | "info" | "success" {
  if (card.signal_state === "Tracking issue") return "attention";
  if (card.signal_state === "Insufficient data" || card.signal_state === "Weak signal") return "info";
  return card.board === "hidden_winner" ? "success" : "critical";
}

function PriorityCards({
  cards,
  shopId,
  window,
}: {
  cards: PriorityCard[];
  shopId: string;
  window: string;
}) {
  if (cards.length === 0) {
    return (
      <Banner tone="info">
        <Text as="p" variant="bodyMd">{messages.dashboard.prioritiesEmpty}</Text>
      </Banner>
    );
  }

  return (
    <InlineGrid columns={{ xs: 1, md: 3 }} gap="400">
      {cards.map((card) => (
        <Card key={`${card.board}-${card.product_id}`}>
          <BlockStack gap="300">
            <InlineStack align="space-between" blockAlign="center">
              <Badge tone={priorityTone(card)}>{priorityBoardLabel(card.board)}</Badge>
              <Badge>{card.signal_state}</Badge>
            </InlineStack>
            <BlockStack gap="100">
              <Text as="h3" variant="headingMd">
                <a
                  href={productPath(card.product_id, shopId, window)}
                  style={{ color: "var(--p-color-text)", textDecoration: "none" }}
                >
                  {card.product_id}
                </a>
              </Text>
              <Text as="p" variant="bodySm" tone="subdued">{card.flag_reason}</Text>
              <InlineStack>
                <Badge>{priorityStepLabel(card.primary_step)}</Badge>
              </InlineStack>
            </BlockStack>
            <BlockStack gap="100">
              {card.evidence.slice(0, 3).map((item) => (
                <Text as="p" key={item} variant="bodySm">{item}</Text>
              ))}
            </BlockStack>
            <BlockStack gap="100">
              <Text as="p" variant="bodyMd">{card.suspected_friction}</Text>
              <Text as="p" variant="bodyMd" fontWeight="semibold">{card.first_fix}</Text>
            </BlockStack>
          </BlockStack>
        </Card>
      ))}
    </InlineGrid>
  );
}

export default function DashboardRoute() {
  const data = useLoaderData<typeof loader>();
  const navigate = useNavigate();

  const tabs = useMemo(
    () =>
      TIME_WINDOWS.map((option) => ({
        id: option.value,
        content: option.label,
        accessibilityLabel: `Show data for ${option.label}`,
      })),
    [],
  );

  const selectedTabIndex = tabs.findIndex((tab) => tab.id === data.window);

  const handleTabChange = useCallback(
    (index: number) => {
      const tab = tabs[index];
      if (tab) {
        void navigate(dashboardPath(data.shopId, tab.id));
      }
    },
    [data.shopId, navigate, tabs],
  );

  const totalTracked = data.blackboard.length + data.redboard.length;
  const primaryProductId = data.priorities[0]?.product_id ?? data.blackboard[0]?.product_id;

  return (
    <Page
      title={messages.app.name}
      subtitle={messages.dashboard.subtitle}
      primaryAction={{
        content: messages.dashboard.viewTopProduct,
        url: primaryProductId
          ? productPath(primaryProductId, data.shopId, data.window)
          : undefined,
        disabled: !primaryProductId,
      }}
    >
      <Layout>
        <Layout.Section>
          <BlockStack gap="400">
            <Banner tone="info">
              <Text as="p" variant="bodyMd">
                {messages.dashboard.bannerText(totalTracked, formatTimeWindowLabel(data.window))}
              </Text>
            </Banner>

            <Tabs tabs={tabs} selected={selectedTabIndex} onSelect={handleTabChange}>
              <Box paddingBlockStart="400">
                <BlockStack gap="500">
                  <BlockStack gap="200">
                    <Text as="h2" variant="headingLg">{messages.dashboard.prioritiesTitle}</Text>
                    <Text as="p" variant="bodyMd" tone="subdued">
                      {messages.dashboard.prioritiesSubtitle}
                    </Text>
                  </BlockStack>
                  <PriorityCards cards={data.priorities} shopId={data.shopId} window={data.window} />
                  <BlockStack gap="300">
                    <Text as="h2" variant="headingMd">{messages.dashboard.viewMoreProducts}</Text>
                    <InlineGrid columns={{ xs: 1, md: 2 }} gap="400">
                      <LeaderboardTable
                        rows={data.redboard}
                        shopId={data.shopId}
                        title={messages.dashboard.redboardTitle}
                        subtitle={messages.dashboard.redboardSubtitle}
                        tone="success"
                        window={data.window}
                      />
                      <LeaderboardTable
                        rows={data.blackboard}
                        shopId={data.shopId}
                        title={messages.dashboard.blackboardTitle}
                        subtitle={messages.dashboard.blackboardSubtitle}
                        tone="critical"
                        window={data.window}
                      />
                    </InlineGrid>
                  </BlockStack>
                </BlockStack>
              </Box>
            </Tabs>
          </BlockStack>
        </Layout.Section>
      </Layout>
    </Page>
  );
}

export function ErrorBoundary() {
  const error = useRouteError();

  let message: string = messages.dashboard.errorMessage;
  if (isRouteErrorResponse(error) && typeof error.data === "string") {
    message = error.data;
  } else if (error instanceof Error) {
    message = error.message;
  }

  return (
    <Page title={messages.app.name}>
      <Layout>
        <Layout.Section>
          <Banner tone="critical">
            <Text as="p" variant="bodyMd">{message}</Text>
          </Banner>
        </Layout.Section>
      </Layout>
    </Page>
  );
}
