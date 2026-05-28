import type { CSSProperties } from "react";
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
import { RecommendationFeedbackButtons } from "@/components/RecommendationFeedback";
import { TIME_WINDOWS, formatTimeWindowLabel } from "@/lib/analytics";
import { fetchIntegrationHealth, fetchLeaderboard, fetchPriorities, parseTimeWindow } from "@/lib/api.server";
import type { IntegrationHealthResponse, PriorityCard, PriorityTrendState, TimeWindow } from "@/lib/contracts";
import { requestIdFromHeaders } from "@/lib/logging";
import { messages } from "@/lib/messages";
import { hostFromUrl, shopIdFromUrl } from "@/lib/shop";
import { dashboardPath, productPath } from "@/lib/url";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const requestId = requestIdFromHeaders(request.headers);
  const shopId = shopIdFromUrl(url);
  const host = hostFromUrl(url);
  const window = parseTimeWindow(url.searchParams.get("window"));
  const [health, priorities, blackboard, redboard] = await Promise.all([
    fetchIntegrationHealth({ requestId, shopId, window }),
    fetchPriorities({ requestId, shopId, window }),
    fetchLeaderboard({ board: "black", requestId, shopId, window }),
    fetchLeaderboard({ board: "red", requestId, shopId, window }),
  ]);

  return { blackboard, health, host, priorities, redboard, shopId, window };
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

export function priorityActionLabel(card: Pick<PriorityCard, "board"> & { card_rank: number }): string {
  if (card.board === "hidden_winner") return "Scale carefully";
  return card.card_rank === 1 ? "Fix first" : "Fix next";
}

const PRIORITY_SECTION_STYLE: CSSProperties = {
  background: "var(--p-color-bg-surface, #ffffff)",
  border: "1px solid var(--p-color-border-secondary, #dcdcdc)",
  borderRadius: "12px",
  boxShadow: "0 2px 8px rgba(0, 0, 0, 0.08)",
};

const PRIORITY_METRICS_STRIP_STYLE: CSSProperties = {
  background: "var(--p-color-bg-surface-secondary, #f9fafb)",
  borderRadius: "10px",
  padding: "0.75rem 0.875rem",
};

const PRIORITY_METRIC_LABEL_STYLE: CSSProperties = {
  whiteSpace: "nowrap",
};

const PRIORITY_MUTED_ROW_STYLE: CSSProperties = {
  color: "var(--p-color-text-subdued)",
};

const PRIORITY_PRODUCT_LINK_STYLE: CSSProperties = {
  color: "var(--p-color-text-link)",
  cursor: "pointer",
  overflowWrap: "anywhere",
  textDecoration: "underline",
  textDecorationThickness: "1px",
  textUnderlineOffset: "3px",
};

function priorityAccentColor(card: Pick<PriorityCard, "board">): string {
  return card.board === "hidden_winner"
    ? "var(--p-color-border-success, #008060)"
    : "var(--p-color-border-critical, #d82c0d)";
}

function priorityActionBackground(card: Pick<PriorityCard, "board">): string {
  return card.board === "hidden_winner"
    ? "rgba(0, 128, 96, 0.05)"
    : "rgba(216, 44, 13, 0.05)";
}

function priorityActionStyle(card: Pick<PriorityCard, "board">): CSSProperties {
  return {
    background: priorityActionBackground(card),
    borderLeft: `6px solid ${priorityAccentColor(card)}`,
    borderRadius: "10px",
    padding: "0.875rem",
  };
}

const PRIORITY_FEEDBACK_STYLE: CSSProperties = {
  borderTop: "1px solid var(--p-color-border-secondary, #e3e3e3)",
  paddingTop: "0.75rem",
};

const PRIORITY_WHY_NOW_STYLE: CSSProperties = {
  borderTop: "1px solid var(--p-color-border-secondary, #e3e3e3)",
  paddingTop: "0.875rem",
};

const PRIORITY_CARD_STYLE: CSSProperties = {
  boxShadow: "0 2px 8px rgba(0, 0, 0, 0.08)",
  borderRadius: "12px",
  overflow: "hidden",
};

function PriorityMetric({ label, value }: { label: string; value: number }) {
  return (
    <BlockStack gap="050">
      <Text as="p" variant="headingLg" fontWeight="bold">
        {value.toLocaleString("en-US")}
      </Text>
      <Text as="p" variant="bodySm" tone="subdued">
        <span style={PRIORITY_METRIC_LABEL_STYLE}>{label}</span>
      </Text>
    </BlockStack>
  );
}

function PriorityMetricsStrip({ card }: { card: PriorityCard }) {
  return (
    <div style={PRIORITY_METRICS_STRIP_STYLE}>
      <InlineGrid columns={3} gap="300">
        <PriorityMetric label="PDP views" value={card.views} />
        <PriorityMetric label="Carts" value={card.add_to_carts} />
        <PriorityMetric label="Orders" value={card.orders} />
      </InlineGrid>
    </div>
  );
}

function PriorityStatusBadges({ card }: { card: PriorityCard }) {
  return (
    <InlineStack gap="100">
      <Badge tone={priorityTrendTone(card.trend_state)}>{card.trend_state}</Badge>
      {prioritySignalTone(card.signal_state) ? (
        <Badge tone={prioritySignalTone(card.signal_state)}>{card.signal_state}</Badge>
      ) : null}
    </InlineStack>
  );
}

function PriorityCardHeader({ card, rank }: { card: PriorityCard; rank: number }) {
  return (
    <BlockStack gap="300">
      <div
        aria-hidden="true"
        style={{
          background: priorityAccentColor(card),
          borderRadius: "2px",
          height: "6px",
        }}
      />
      <InlineStack align="space-between" blockAlign="center" gap="200">
        <InlineStack gap="200" blockAlign="center">
          <Text as="span" variant="headingLg">
            #{rank}
          </Text>
          <Badge tone={priorityTone(card)}>{priorityActionLabel({ board: card.board, card_rank: rank })}</Badge>
        </InlineStack>
        <PriorityStatusBadges card={card} />
      </InlineStack>
    </BlockStack>
  );
}

function PriorityProductSummary({
  card,
  host,
  shopId,
  window,
}: {
  card: PriorityCard;
  host?: string;
  shopId: string;
  window: TimeWindow;
}) {
  return (
    <BlockStack gap="200">
      <Text as="h3" variant="headingMd">
        <a
          aria-label={`View product details for ${card.product_id}`}
          href={productPath(card.product_id, shopId, window, host)}
          style={PRIORITY_PRODUCT_LINK_STYLE}
        >
          {card.product_id}
        </a>
      </Text>
      <InlineStack gap="100" blockAlign="center">
        <Badge tone={priorityTone(card)}>{priorityBoardLabel(card.board)}</Badge>
        <Text as="span" variant="bodySm" tone="subdued">
          {card.flag_reason}
        </Text>
      </InlineStack>
      <Text as="p" variant="bodySm" tone="subdued">
        <span style={PRIORITY_MUTED_ROW_STYLE}>{priorityStepLabel(card.primary_step)}</span>
      </Text>
      <Text as="p" variant="bodySm" tone="subdued">{card.trend_reason}</Text>
    </BlockStack>
  );
}

function PriorityRecommendation({ card }: { card: PriorityCard }) {
  return (
    <div style={priorityActionStyle(card)}>
      <BlockStack gap="100">
        <InlineStack gap="150" blockAlign="center">
          <Text as="span" variant="bodySm">💡</Text>
          <Text as="p" variant="bodySm" tone="subdued">
            {messages.dashboard.priorityRecommendedMove}
          </Text>
        </InlineStack>
        <Text as="p" variant="bodyMd" fontWeight="semibold">
          {card.first_fix}
        </Text>
      </BlockStack>
    </div>
  );
}

function PriorityWhyNow({ card }: { card: PriorityCard }) {
  return (
    <div style={PRIORITY_WHY_NOW_STYLE}>
      <BlockStack gap="150">
        <Text as="p" variant="bodySm" tone="subdued">
          {messages.dashboard.priorityWhyNow}
        </Text>
        <Text as="p" variant="bodyMd">{card.suspected_friction}</Text>
        {card.evidence.slice(0, 2).map((item) => (
          <Text as="p" key={item} variant="bodySm" tone="subdued">{item}</Text>
        ))}
      </BlockStack>
    </div>
  );
}

function PriorityFeedback({
  card,
  shopId,
  window,
}: {
  card: PriorityCard;
  shopId: string;
  window: TimeWindow;
}) {
  return (
    <div style={PRIORITY_FEEDBACK_STYLE}>
      <RecommendationFeedbackButtons
        board={card.board}
        productId={card.product_id}
        shopId={shopId}
        window={window}
      />
    </div>
  );
}

function PriorityCardContent({
  card,
  host,
  rank,
  shopId,
  window,
}: {
  card: PriorityCard;
  host?: string;
  rank: number;
  shopId: string;
  window: TimeWindow;
}) {
  return (
    <BlockStack gap="400">
      <PriorityCardHeader card={card} rank={rank} />
      <PriorityProductSummary card={card} host={host} shopId={shopId} window={window} />
      <PriorityMetricsStrip card={card} />
      <PriorityRecommendation card={card} />
      <PriorityWhyNow card={card} />
      <PriorityFeedback card={card} shopId={shopId} window={window} />
    </BlockStack>
  );
}

export function priorityTrendTone(
  trend: PriorityTrendState,
): "critical" | "success" | "info" | undefined {
  if (trend === "Worsening") return "critical";
  if (trend === "Improving") return "success";
  if (trend === "New") return "info";
  return undefined;
}

export function prioritySignalTone(
  signalState: PriorityCard["signal_state"],
): "attention" | "info" | undefined {
  if (signalState === "Tracking issue") return "attention";
  if (signalState === "Insufficient data" || signalState === "Weak signal") return "info";
  return undefined;
}

export function healthBannerContent(
  health: IntegrationHealthResponse,
): { message: string; tone: "critical" | "info" | "success" | "warning" } {
  if (health.status === "healthy") {
    return {
      message: "Integration healthy: tracker, PDP, buy-box, and order coverage are present.",
      tone: "success",
    };
  }

  if (health.status === "not_connected") {
    return {
      message: "Integration not connected: check the theme app embed and ingest event delivery.",
      tone: "critical",
    };
  }

  const missing = health.checks
    .filter((check) => check.status === "missing")
    .map((check) => check.label);
  const missingText = missing.length > 0
    ? missing.length === 1
      ? missing[0]
      : `${missing.slice(0, -1).join(", ")} and ${missing[missing.length - 1]}`
    : "some event coverage";

  return {
    message: `Integration partial: missing ${missingText}.`,
    tone: "warning",
  };
}

export function readinessBannerContent(
  health: IntegrationHealthResponse,
): { message: string; tone: "critical" | "info" | "success" | "warning" } {
  const installationOk = health.checks.some(
    (check) => check.key === "installation" && check.status === "ok",
  );
  if (!installationOk && health.status === "not_connected") {
    return {
      message: "No installation record: install SKU Lens before enabling storefront tracking.",
      tone: "critical",
    };
  }

  if (!health.last_event_at) {
    return {
      message: "No raw storefront events yet: enable the theme app embed, then open a product page.",
      tone: "warning",
    };
  }

  if (health.coverage.views === 0) {
    return {
      message: `Raw events are arriving, but no PDP views are present yet. Last raw event: ${health.last_event_at}.`,
      tone: "warning",
    };
  }

  if (health.coverage.views < 10) {
    return {
      message: `Only ${health.coverage.views} PDP views in this window. Priority cards may stay low-confidence until more traffic arrives.`,
      tone: "info",
    };
  }

  if (health.status === "partial") {
    const missing = health.checks
      .filter((check) => check.status === "missing")
      .map((check) => check.label);
    return {
      message: `Partial coverage: ${missing.join(", ") || "some events"} still missing. Last raw event: ${health.last_event_at}.`,
      tone: "warning",
    };
  }

  return {
    message: `Tracking is healthy. Last raw event: ${health.last_event_at}.`,
    tone: "success",
  };
}

function PriorityCards({
  cards,
  host,
  shopId,
  window,
}: {
  cards: PriorityCard[];
  host?: string;
  shopId: string;
  window: TimeWindow;
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
      {cards.map((card, index) => (
        <div key={`${card.board}-${card.product_id}`} style={PRIORITY_CARD_STYLE}>
          <Card>
            <PriorityCardContent card={card} host={host} rank={index + 1} shopId={shopId} window={window} />
          </Card>
        </div>
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
        void navigate(dashboardPath(data.shopId, tab.id, data.host));
      }
    },
    [data.host, data.shopId, navigate, tabs],
  );

  const totalTracked = data.blackboard.length + data.redboard.length;
  const primaryProductId = data.priorities[0]?.product_id ?? data.blackboard[0]?.product_id;
  const integrationHealth = readinessBannerContent(data.health);

  return (
    <Page
      title={messages.app.name}
      subtitle={messages.dashboard.subtitle}
      primaryAction={{
        content: messages.dashboard.viewTopProduct,
        url: primaryProductId
          ? productPath(primaryProductId, data.shopId, data.window, data.host)
          : undefined,
        disabled: !primaryProductId,
      }}
    >
      <Layout>
        <Layout.Section>
          <BlockStack gap="400">
            <Banner tone={integrationHealth.tone}>
              <Text as="p" variant="bodyMd">
                {integrationHealth.message}
              </Text>
            </Banner>
            <Banner tone="info">
              <Text as="p" variant="bodyMd">
                {messages.dashboard.bannerText(totalTracked, formatTimeWindowLabel(data.window))}
              </Text>
            </Banner>

            <Tabs tabs={tabs} selected={selectedTabIndex} onSelect={handleTabChange}>
              <Box paddingBlockStart="400">
                <BlockStack gap="500">
                  <div style={PRIORITY_SECTION_STYLE}>
                    <Box padding="400">
                      <BlockStack gap="400">
                        <InlineStack align="space-between" blockAlign="start" gap="300">
                          <BlockStack gap="200">
                            <InlineStack gap="200" blockAlign="center">
                              <Badge tone="info">{messages.dashboard.prioritiesKicker}</Badge>
                            </InlineStack>
                            <Text as="h2" variant="headingLg">{messages.dashboard.prioritiesTitle}</Text>
                            <Text as="p" variant="bodyMd" tone="subdued">
                              {messages.dashboard.prioritiesSubtitle}
                            </Text>
                          </BlockStack>
                          <Badge>{messages.dashboard.prioritiesActionCount(data.priorities.length)}</Badge>
                        </InlineStack>
                        <PriorityCards
                          cards={data.priorities}
                          host={data.host}
                          shopId={data.shopId}
                          window={data.window}
                        />
                      </BlockStack>
                    </Box>
                  </div>
                  <BlockStack gap="300">
                    <Text as="h2" variant="headingMd">{messages.dashboard.viewMoreProducts}</Text>
                    <InlineGrid columns={{ xs: 1, md: 2 }} gap="400">
                      <LeaderboardTable
                        host={data.host}
                        rows={data.redboard}
                        shopId={data.shopId}
                        title={messages.dashboard.redboardTitle}
                        subtitle={messages.dashboard.redboardSubtitle}
                        tone="success"
                        window={data.window}
                      />
                      <LeaderboardTable
                        host={data.host}
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
