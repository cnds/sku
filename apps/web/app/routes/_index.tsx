import type { CSSProperties } from "react";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";
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
  Text,
} from "@shopify/polaris";

import { LeaderboardTable } from "@/components/LeaderboardTable";
import { MarkdownText } from "@/components/MarkdownText";
import { PageBottomSpacer } from "@/components/PageBottomSpacer";
import { RecommendationFeedbackButtons } from "@/components/RecommendationFeedback";
import { TIME_WINDOWS, formatTimeWindowLabel } from "@/lib/analytics";
import { fetchIntegrationHealth, fetchLeaderboard, fetchPriorities, parseTimeWindow } from "@/lib/api.server";
import type { IntegrationHealthResponse, PriorityCard, TimeWindow } from "@/lib/contracts";
import { requestIdFromHeaders } from "@/lib/logging";
import { messages } from "@/lib/messages";
import {
  priorityAccentColor,
  priorityActionLabel,
  priorityActionStyle,
  priorityBoardLabel,
  prioritySignalTone,
  priorityStepLabel,
  priorityTone,
  priorityTrendTone,
} from "@/lib/priorities";
import { hostFromUrl, shopIdFromUrl } from "@/lib/shop";
import { BORDER_SECONDARY, CARD_BORDER_RADIUS, CARD_SHADOW, INNER_BORDER_RADIUS } from "@/lib/tokens";
import { dashboardPath, productPath } from "@/lib/url";
import interactiveStyles from "@/styles/interactive.module.css";

export {
  priorityActionLabel,
  priorityActionStyle,
  prioritySignalTone,
  priorityStepLabel,
  priorityTrendTone,
} from "@/lib/priorities";

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

const PRIORITY_SECTION_STYLE: CSSProperties = {
  background: "var(--p-color-bg-surface)",
  border: `1px solid ${BORDER_SECONDARY}`,
  borderRadius: CARD_BORDER_RADIUS,
  boxShadow: CARD_SHADOW,
};

const PRIORITY_METRICS_STRIP_STYLE: CSSProperties = {
  background: "var(--p-color-bg-surface-secondary)",
  borderRadius: INNER_BORDER_RADIUS,
  padding: "0.75rem",
};

const PRIORITY_METRIC_LABEL_STYLE: CSSProperties = {
  whiteSpace: "nowrap",
};

const PRIORITY_MUTED_ROW_STYLE: CSSProperties = {
  color: "var(--p-color-text-subdued)",
};

const PRIORITY_MARKDOWN_BODY_STYLE: CSSProperties = {
  fontSize: "var(--p-font-size-325, 0.875rem)",
  lineHeight: 1.5,
};

const PRIORITY_MARKDOWN_SEMIBOLD_STYLE: CSSProperties = {
  ...PRIORITY_MARKDOWN_BODY_STYLE,
  fontWeight: 600,
};

const PRIORITY_MARKDOWN_SUBDUED_STYLE: CSSProperties = {
  color: "var(--p-color-text-subdued)",
  fontSize: "var(--p-font-size-300, 0.8125rem)",
  lineHeight: 1.4,
};

const PRIORITY_DIVIDER_STYLE: CSSProperties = {
  borderTop: `1px solid ${BORDER_SECONDARY}`,
  paddingBottom: "0.25rem",
  paddingTop: "0.75rem",
};

const PRIORITY_CARD_STYLE: CSSProperties = {
  boxShadow: CARD_SHADOW,
  borderRadius: CARD_BORDER_RADIUS,
  overflow: "hidden",
};

const TIME_WINDOW_SELECTOR_STYLE: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "0.5rem",
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

export function TimeWindowSelector({
  host,
  selectedWindow,
  shopId,
}: {
  host?: string;
  selectedWindow: TimeWindow;
  shopId: string;
}) {
  return (
    <nav aria-label="Analytics window" style={TIME_WINDOW_SELECTOR_STYLE}>
      {TIME_WINDOWS.map((option) => {
        const isSelected = option.value === selectedWindow;
        return (
          <a
            aria-current={isSelected ? "page" : undefined}
            aria-label={`Show data for ${option.label}`}
            className={isSelected
              ? `${interactiveStyles.timeWindowOption} ${interactiveStyles.timeWindowOptionActive}`
              : interactiveStyles.timeWindowOption}
            data-selected={isSelected ? "true" : undefined}
            href={dashboardPath(shopId, option.value, host)}
            key={option.value}
          >
            {option.label}
          </a>
        );
      })}
    </nav>
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
          className={interactiveStyles.productLink}
          href={productPath(card.product_id, shopId, window, host)}
        >
          {card.product_id}
        </a>
      </Text>
      <InlineStack gap="100" blockAlign="center">
        <Badge tone={priorityTone(card)}>{priorityBoardLabel(card.board)}</Badge>
        <div style={PRIORITY_MARKDOWN_SUBDUED_STYLE}>
          <MarkdownText markdown={card.flag_reason} fallback="" />
        </div>
      </InlineStack>
      <Text as="p" variant="bodySm" tone="subdued">
        <span style={PRIORITY_MUTED_ROW_STYLE}>{priorityStepLabel(card.primary_step)}</span>
      </Text>
      <div style={PRIORITY_MARKDOWN_SUBDUED_STYLE}>
        <MarkdownText markdown={card.trend_reason} fallback="" />
      </div>
    </BlockStack>
  );
}

export function PriorityRecommendation({ card }: { card: PriorityCard }) {
  return (
    <div style={priorityActionStyle(card)}>
      <BlockStack gap="100">
        <InlineStack gap="150" blockAlign="center">
          <Text as="span" variant="bodySm">💡</Text>
          <Text as="p" variant="bodySm" tone="subdued">
            {messages.dashboard.priorityRecommendedMove}
          </Text>
        </InlineStack>
        <div style={PRIORITY_MARKDOWN_SEMIBOLD_STYLE}>
          <MarkdownText markdown={card.first_fix} fallback="—" />
        </div>
      </BlockStack>
    </div>
  );
}

export function PriorityWhyNow({ card }: { card: PriorityCard }) {
  return (
    <div style={PRIORITY_DIVIDER_STYLE}>
      <BlockStack gap="150">
        <Text as="p" variant="bodySm" tone="subdued">
          {messages.dashboard.priorityWhyNow}
        </Text>
        <div style={PRIORITY_MARKDOWN_BODY_STYLE}>
          <MarkdownText markdown={card.suspected_friction} fallback="—" />
        </div>
        {card.evidence.slice(0, 2).map((item) => (
          <div key={item} style={PRIORITY_MARKDOWN_SUBDUED_STYLE}>
            <MarkdownText markdown={item} fallback="—" />
          </div>
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
    <div style={PRIORITY_DIVIDER_STYLE}>
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

            <TimeWindowSelector host={data.host} selectedWindow={data.window} shopId={data.shopId} />

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
              <PageBottomSpacer />
            </BlockStack>
          </BlockStack>
        </Layout.Section>
      </Layout>
    </Page>
  );
}

export function ErrorBoundary() {
  return (
    <Page title={messages.app.name}>
      <Layout>
        <Layout.Section>
          <Banner tone="critical">
            <Text as="p" variant="bodyMd">{messages.dashboard.errorMessage}</Text>
          </Banner>
        </Layout.Section>
      </Layout>
    </Page>
  );
}
