import type { CSSProperties } from "react";
import { startTransition, useEffect, useState } from "react";
import {
  Badge,
  Banner,
  BlockStack,
  Box,
  Button,
  Card,
  InlineGrid,
  InlineStack,
  SkeletonBodyText,
  Spinner,
  Text,
} from "@shopify/polaris";
import { RefreshIcon } from "@shopify/polaris-icons";
import { MarkdownText } from "@/components/MarkdownText";
import type { DiagnosisResult, PriorityCard, ProductAnalysisResult } from "@/lib/contracts";
import { BORDER_SECONDARY, INNER_BORDER_RADIUS } from "@/lib/tokens";

import {
  createFailedDiagnosis,
  createPendingDiagnosis,
  diagnosisFreshnessText,
  diagnosisRerunPath,
  parseDiagnosisSections,
  snapshotFromAnalysis,
} from "@/lib/diagnosis";
import { REQUEST_ID_HEADER, generateRequestId, logBrowserEvent } from "@/lib/logging";
import { messages } from "@/lib/messages";
import {
  priorityAccentColor,
  priorityActionBackground,
  priorityActionLabel,
  priorityBoardLabel,
  prioritySignalTone,
  priorityStepLabel,
  priorityTone,
  priorityTrendTone,
} from "@/lib/priorities";

interface AnalysisPanelProps {
  analysis: ProductAnalysisResult;
  diagnosisPath: string;
  priorityCard?: PriorityCard | null;
}

const DIAGNOSIS_POLL_INTERVAL_MS = 3_000;

const PRIORITY_DETAIL_STYLE: CSSProperties = {
  borderRadius: INNER_BORDER_RADIUS,
  overflow: "hidden",
};

const PRIORITY_DETAIL_BODY_STYLE: CSSProperties = {
  padding: "1rem",
};

const JOURNEY_STEP_STYLE: CSSProperties = {
  background: "var(--p-color-bg-surface, #ffffff)",
  border: `1px solid ${BORDER_SECONDARY}`,
  borderRadius: INNER_BORDER_RADIUS,
  padding: "0.75rem",
};

const JOURNEY_INSIGHT_STYLE: CSSProperties = {
  background: "var(--p-color-bg-fill-critical-secondary, #fff4f4)",
  border: "1px solid var(--p-color-border-critical, #d82c0d)",
  borderRadius: INNER_BORDER_RADIUS,
  padding: "1rem",
};

const JOURNEY_INSIGHT_LIST_STYLE: CSSProperties = {
  margin: 0,
  paddingLeft: "1.25rem",
};

const MARKDOWN_BODY_STYLE: CSSProperties = {
  fontSize: "var(--p-font-size-325, 0.875rem)",
  lineHeight: 1.5,
};

const MARKDOWN_SEMIBOLD_STYLE: CSSProperties = {
  ...MARKDOWN_BODY_STYLE,
  fontWeight: 600,
};

const MARKDOWN_SUBDUED_STYLE: CSSProperties = {
  color: "var(--p-color-text-subdued)",
  fontSize: "var(--p-font-size-300, 0.8125rem)",
  lineHeight: 1.4,
};

interface ShopperJourneyStep {
  id: string;
  label: string;
  value: string;
  detail: string;
}

interface ShopperJourneyDropOff {
  stepId: string;
  label: string;
  evidence: string;
  suspectedFriction: string;
  firstFix: string;
}

interface ShopperJourney {
  steps: ShopperJourneyStep[];
  primaryDropOff: ShopperJourneyDropOff;
}

function priorityDetailStyle(card: Pick<PriorityCard, "board">): CSSProperties {
  return {
    ...PRIORITY_DETAIL_STYLE,
    borderLeft: `6px solid ${priorityAccentColor(card)}`,
  };
}

function priorityConclusionStyle(card: Pick<PriorityCard, "board">): CSSProperties {
  return {
    background: priorityActionBackground(card),
    border: `1px solid ${priorityAccentColor(card)}`,
    borderRadius: INNER_BORDER_RADIUS,
    padding: "1rem",
  };
}

function journeyInsightStyle(priorityCard?: PriorityCard | null): CSSProperties {
  if (!priorityCard) {
    return JOURNEY_INSIGHT_STYLE;
  }

  return {
    ...JOURNEY_INSIGHT_STYLE,
    background: priorityActionBackground(priorityCard),
    border: `1px solid ${priorityAccentColor(priorityCard)}`,
  };
}

function journeyStepIdForPriority(step: string): string | null {
  if (step === "collection_click") return "click";
  if (step === "data_volume" || step === "pdp_decision" || step === "tracking_coverage") return "pdp_view";
  if (step === "merchandising_reach") return "exposure";
  if (step === "pdp_add_to_cart") return "add_to_cart";
  if (step === "cart_to_order") return "order";
  return null;
}

function journeyStepStyle({
  isActive,
  priorityCard,
}: {
  isActive: boolean;
  priorityCard?: PriorityCard | null;
}): CSSProperties {
  if (!isActive) {
    return JOURNEY_STEP_STYLE;
  }

  if (priorityCard) {
    return {
      ...JOURNEY_STEP_STYLE,
      background: priorityActionBackground(priorityCard),
      border: `1px solid ${priorityAccentColor(priorityCard)}`,
    };
  }

  return {
    ...JOURNEY_STEP_STYLE,
    background: "var(--p-color-bg-fill-critical-secondary, #fff4f4)",
    border: "1px solid var(--p-color-border-critical, #d82c0d)",
  };
}

function PriorityDetailCard({ card }: { card: PriorityCard }) {
  return (
    <Card padding="0">
      <div style={priorityDetailStyle(card)}>
        <div style={PRIORITY_DETAIL_BODY_STYLE}>
          <BlockStack gap="400">
            <InlineStack align="space-between" blockAlign="start" gap="300">
              <BlockStack gap="200">
                <InlineStack gap="200" blockAlign="center">
                  <Badge tone={priorityTone(card)}>{priorityActionLabel(card)}</Badge>
                  <Badge tone={priorityTone(card)}>{priorityBoardLabel(card.board)}</Badge>
                  <Badge tone={priorityTrendTone(card.trend_state)}>{card.trend_state}</Badge>
                  {prioritySignalTone(card.signal_state) ? (
                    <Badge tone={prioritySignalTone(card.signal_state)}>{card.signal_state}</Badge>
                  ) : null}
                </InlineStack>
                <Text as="h2" variant="headingMd">{messages.analysis.priorityDetailHeading}</Text>
                <Text as="p" variant="bodySm" tone="subdued">
                  {priorityStepLabel(card.primary_step)}
                </Text>
              </BlockStack>
              <Text as="p" variant="bodySm" tone="subdued">
                {card.window_start_date} to {card.window_end_date}
              </Text>
            </InlineStack>

            <div style={priorityConclusionStyle(card)}>
              <BlockStack gap="100">
                <Text as="p" variant="bodySm" tone="subdued">
                  {messages.analysis.priorityConclusion}
                </Text>
                <div style={MARKDOWN_SEMIBOLD_STYLE}>
                  <MarkdownText markdown={card.first_fix} fallback="—" />
                </div>
                <div style={MARKDOWN_SUBDUED_STYLE}>
                  <MarkdownText markdown={card.trend_reason} fallback="" />
                </div>
              </BlockStack>
            </div>
          </BlockStack>
        </div>
      </div>
    </Card>
  );
}

export function buildShopperJourney(analysis: ProductAnalysisResult): ShopperJourney {
  const target = analysis.funnel.target;
  const benchmark = analysis.funnel.benchmark;
  const targetViewToCart = safeRate(target.add_to_carts, target.views);
  const benchmarkViewToCart = safeRate(benchmark.add_to_carts, benchmark.views);
  const targetCartToOrder = safeRate(target.orders, target.add_to_carts);
  const benchmarkCartToOrder = safeRate(benchmark.orders, benchmark.add_to_carts);
  const targetCollectionCtr = safeRate(target.clicks, target.impressions);
  const benchmarkCollectionCtr = safeRate(benchmark.clicks, benchmark.impressions);
  const engagementCount = safeNumber(target.media_interactions) + safeNumber(target.variant_changes)
    + Object.values(target.component_clicks_distribution ?? {}).reduce((sum, value) => sum + value, 0);

  return {
    primaryDropOff: primaryDropOff({
      benchmarkCartToOrder,
      benchmarkCollectionCtr,
      benchmarkViewToCart,
      targetCartToOrder,
      targetCollectionCtr,
      targetViewToCart,
    }),
    steps: [
      {
        detail: `${formatCount(target.impressions)} tracked impressions`,
        id: "exposure",
        label: messages.analysis.dimensionExposure,
        value: formatCount(target.impressions),
      },
      {
        detail: `${formatPercent(targetCollectionCtr)} collection CTR`,
        id: "click",
        label: messages.analysis.dimensionClick,
        value: formatCount(target.clicks),
      },
      {
        detail: `${formatCount(target.views)} PDP sessions`,
        id: "pdp_view",
        label: messages.analysis.dimensionPdpView,
        value: formatCount(target.views),
      },
      {
        detail: `${formatCount(engagementCount)} media, variant, and component actions`,
        id: "engagement",
        label: messages.analysis.dimensionEngagement,
        value: formatCount(engagementCount),
      },
      {
        detail: `${formatPercent(targetViewToCart)} PDP view to add-to-cart`,
        id: "add_to_cart",
        label: messages.analysis.dimensionAddToCart,
        value: formatCount(target.add_to_carts),
      },
      {
        detail: `${formatPercent(targetCartToOrder)} cart-to-order`,
        id: "order",
        label: messages.analysis.dimensionOrders,
        value: formatCount(target.orders),
      },
    ],
  };
}

function primaryDropOff(args: {
  benchmarkCartToOrder: number;
  benchmarkCollectionCtr: number;
  benchmarkViewToCart: number;
  targetCartToOrder: number;
  targetCollectionCtr: number;
  targetViewToCart: number;
}): ShopperJourneyDropOff {
  if (args.benchmarkCollectionCtr - args.targetCollectionCtr > 0.05) {
    return {
      evidence: `${formatPercent(args.targetCollectionCtr)} collection CTR`,
      firstFix: "Clarify the collection card image, title, or price cue before the next traffic push.",
      label: "Collection impression to click",
      stepId: "collection_click",
      suspectedFriction: "The product is being seen, but the listing is not earning enough PDP visits.",
    };
  }

  if (args.benchmarkViewToCart - args.targetViewToCart > 0.05) {
    return {
      evidence: `${formatPercent(args.targetViewToCart)} PDP view to add-to-cart`,
      firstFix: "Move the strongest trust, fit, or offer cue next to the buy box and test one change.",
      label: "PDP view to add-to-cart",
      stepId: "pdp_add_to_cart",
      suspectedFriction: "Shoppers reach the page but do not get enough confidence to start checkout.",
    };
  }

  if (args.benchmarkCartToOrder - args.targetCartToOrder > 0.1) {
    return {
      evidence: `${formatPercent(args.targetCartToOrder)} cart-to-order`,
      firstFix: "Clarify shipping, returns, or checkout confidence near the CTA.",
      label: "Add-to-cart to order",
      stepId: "cart_to_order",
      suspectedFriction: "Buy-box intent is present, but shoppers hesitate before completing the order.",
    };
  }

  return {
    evidence: "No single journey step trails the benchmark sharply.",
    firstFix: "Keep monitoring the next window before making a large page change.",
    label: "No sharp drop-off",
    stepId: "balanced",
    suspectedFriction: "The journey does not show a dominant loss point yet.",
  };
}

function safeNumber(value: number | undefined): number {
  return value ?? 0;
}

function safeRate(numerator: number | undefined, denominator: number | undefined): number {
  const safeDenominator = safeNumber(denominator);
  return safeDenominator === 0 ? 0 : safeNumber(numerator) / safeDenominator;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatCount(value: number | undefined): string {
  return safeNumber(value).toLocaleString("en-US");
}

function ShopperJourneyCard({
  analysis,
  priorityCard,
}: {
  analysis: ProductAnalysisResult;
  priorityCard?: PriorityCard | null;
}) {
  const journey = buildShopperJourney(analysis);
  const headerBadge = priorityCard ? priorityStepLabel(priorityCard.primary_step) : messages.analysis.primaryDropOff;
  const headerTone = priorityCard ? priorityTone(priorityCard) : "critical";
  const highlightedStepId = priorityCard
    ? journeyStepIdForPriority(priorityCard.primary_step)
    : journey.primaryDropOff.stepId;
  const insightTitle = priorityCard ? messages.analysis.priorityWhyNow : journey.primaryDropOff.label;
  const insightEvidence = priorityCard ? priorityCard.evidence : [journey.primaryDropOff.evidence];
  const insightFriction = priorityCard ? priorityCard.suspected_friction : journey.primaryDropOff.suspectedFriction;
  const insightFirstFix = priorityCard ? null : journey.primaryDropOff.firstFix;

  return (
    <Card>
      <BlockStack gap="400">
        <InlineStack align="space-between" blockAlign="center">
          <Text as="h2" variant="headingMd">{messages.analysis.journeyHeading}</Text>
          <Badge tone={headerTone}>{headerBadge}</Badge>
        </InlineStack>
        <InlineGrid columns={{ xs: 2, md: 6 }} gap="300">
          {journey.steps.map((step) => (
            <div
              key={step.id}
              style={journeyStepStyle({
                isActive: step.id === highlightedStepId,
                priorityCard,
              })}
            >
              <BlockStack gap="100">
                <Text as="p" variant="bodySm" tone="subdued">{step.label}</Text>
                <Text as="p" variant="headingMd">{step.value}</Text>
                <Text as="p" variant="bodySm" tone="subdued">{step.detail}</Text>
              </BlockStack>
            </div>
          ))}
        </InlineGrid>
        <div style={journeyInsightStyle(priorityCard)}>
          <BlockStack gap="200">
            <Text as="h3" variant="headingSm">{insightTitle}</Text>
            {insightEvidence.length === 1 ? (
              <div style={MARKDOWN_BODY_STYLE}>
                <MarkdownText markdown={insightEvidence[0] ?? ""} fallback="—" />
              </div>
            ) : (
              <ul style={JOURNEY_INSIGHT_LIST_STYLE}>
                {insightEvidence.map((item) => (
                  <li key={item}>
                    <div style={MARKDOWN_BODY_STYLE}>
                      <MarkdownText markdown={item} fallback="—" />
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <div style={MARKDOWN_BODY_STYLE}>
              <MarkdownText markdown={insightFriction} fallback="—" />
            </div>
            {insightFirstFix ? (
              <div style={MARKDOWN_SEMIBOLD_STYLE}>
                <MarkdownText markdown={insightFirstFix} fallback="—" />
              </div>
            ) : null}
          </BlockStack>
        </div>
      </BlockStack>
    </Card>
  );
}

function DiagnosisHeader({
  diagnosis,
  onRerun,
  showRerun,
}: {
  diagnosis: DiagnosisResult;
  onRerun: () => void;
  showRerun: boolean;
}) {
  return (
    <InlineStack align="space-between" blockAlign="center" gap="300">
      <InlineStack gap="200" blockAlign="center">
        {diagnosis.status === "pending" ? <Spinner size="small" /> : null}
        <Text as="h2" variant="headingMd">
          {messages.analysis.diagnosisHeading}
        </Text>
        {diagnosis.status === "ready" ? <Badge tone="success">{messages.analysis.diagnosisReady}</Badge> : null}
        {diagnosis.status === "pending" ? <Badge tone="attention">{messages.analysis.diagnosisGenerating}</Badge> : null}
        {diagnosis.status === "failed" ? <Badge tone="critical">{messages.analysis.diagnosisFailed}</Badge> : null}
      </InlineStack>
      {showRerun ? (
        <Button icon={RefreshIcon} onClick={onRerun} size="slim">
          Re-run
        </Button>
      ) : null}
    </InlineStack>
  );
}

function DiagnosisCards({
  diagnosis,
  onRerun,
}: {
  diagnosis: DiagnosisResult;
  onRerun: () => void;
}) {
  if (diagnosis.status === "pending") {
    return (
      <Card>
        <BlockStack gap="400">
          <DiagnosisHeader diagnosis={diagnosis} onRerun={onRerun} showRerun={false} />
          <Text as="p" variant="bodySm" tone="subdued">{diagnosisFreshnessText(diagnosis)}</Text>
          <Banner tone="info">
            {messages.analysis.diagnosisPendingBanner}
          </Banner>
          <SkeletonBodyText lines={4} />
        </BlockStack>
      </Card>
    );
  }

  if (diagnosis.status === "failed") {
    return (
      <Card>
        <BlockStack gap="300">
          <DiagnosisHeader diagnosis={diagnosis} onRerun={onRerun} showRerun />
          <Text as="p" variant="bodySm" tone="subdued">{diagnosisFreshnessText(diagnosis)}</Text>
          <Banner tone="critical">
            {diagnosis.report_markdown ?? messages.analysis.diagnosisFailedFallback}
          </Banner>
        </BlockStack>
      </Card>
    );
  }

  const { evidence, firstFix, observed, suspectedFriction } = parseDiagnosisSections(diagnosis.report_markdown);

  const cards: Array<{ title: string; content: string; toneColor: string; bgColor: string; borderColor: string }> = [
    {
      title: messages.analysis.cardObserved,
      content: observed,
      toneColor: "var(--p-color-text-warning)",
      bgColor: "var(--p-color-bg-fill-warning-secondary)",
      borderColor: "var(--p-color-border-warning)",
    },
    {
      title: messages.analysis.cardEvidence,
      content: evidence,
      toneColor: "var(--p-color-text)",
      bgColor: "var(--p-color-bg-surface-secondary)",
      borderColor: BORDER_SECONDARY,
    },
    {
      title: messages.analysis.cardSuspectedFriction,
      content: suspectedFriction,
      toneColor: "var(--p-color-text-info)",
      bgColor: "var(--p-color-bg-fill-info-secondary)",
      borderColor: "var(--p-color-border-info)",
    },
    {
      title: messages.analysis.cardFirstFix,
      content: firstFix,
      toneColor: "var(--p-color-text-success)",
      bgColor: "var(--p-color-bg-fill-success-secondary)",
      borderColor: "var(--p-color-border-success)",
    },
  ];

  return (
    <Box>
      <Box paddingBlockEnd="300">
        <BlockStack gap="100">
          <DiagnosisHeader diagnosis={diagnosis} onRerun={onRerun} showRerun />
          <Text as="p" variant="bodySm" tone="subdued">{diagnosisFreshnessText(diagnosis)}</Text>
        </BlockStack>
      </Box>
      <InlineGrid columns={{ xs: 1, md: 2 }} gap="400">
        {cards.map((card) => (
          <div
            key={card.title}
            style={{
              border: `1px solid ${card.borderColor}`,
              borderRadius: INNER_BORDER_RADIUS,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                background: card.bgColor,
                color: card.toneColor,
                fontSize: "var(--p-font-size-300, 0.8125rem)",
                fontWeight: "bold",
                padding: "0.75rem 1rem",
              }}
            >
              {card.title}
            </div>
            <div style={{ color: "var(--p-color-text)", fontSize: "var(--p-font-size-300, 0.8125rem)", lineHeight: 1.6, padding: "1rem", whiteSpace: "pre-wrap" }}>
              <MarkdownText markdown={card.content} fallback="—" />
            </div>
          </div>
        ))}
      </InlineGrid>
    </Box>
  );
}

export function AnalysisPanel({ analysis, diagnosisPath, priorityCard }: AnalysisPanelProps) {
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult>(createPendingDiagnosis);
  const [rerunToken, setRerunToken] = useState(0);

  useEffect(() => {
    const abortController = new AbortController();
    let pollTimer: number | undefined;
    let forceConsumed = false;

    async function fetchDiagnosis(init?: RequestInit, path = diagnosisPath): Promise<DiagnosisResult> {
      const requestId = generateRequestId();
      const headers = new Headers(init?.headers);
      headers.set(REQUEST_ID_HEADER, requestId);
      const response = await fetch(path, {
        ...init,
        headers,
        signal: abortController.signal,
      });

      if (response.status === 404 && init?.method !== "POST") {
        return fetchDiagnosis({
          body: JSON.stringify(snapshotFromAnalysis(analysis)),
          headers: { "Content-Type": "application/json" },
          method: "POST",
        });
      }

      if (!response.ok) {
        const error = new Error(`Diagnosis request failed with status ${response.status}.`);
        (error as Error & { requestId: string; status: number }).requestId = requestId;
        (error as Error & { requestId: string; status: number }).status = response.status;
        throw error;
      }

      return (await response.json()) as DiagnosisResult;
    }

    function schedulePoll() {
      pollTimer = window.setTimeout(() => {
        void syncDiagnosis();
      }, DIAGNOSIS_POLL_INTERVAL_MS);
    }

    async function syncDiagnosis() {
      try {
        const shouldForce = rerunToken > 0 && !forceConsumed;
        forceConsumed = forceConsumed || shouldForce;
        const nextDiagnosis = shouldForce
          ? await fetchDiagnosis(
            {
              body: JSON.stringify(snapshotFromAnalysis(analysis)),
              headers: { "Content-Type": "application/json" },
              method: "POST",
            },
            diagnosisRerunPath(diagnosisPath),
          )
          : await fetchDiagnosis();
        startTransition(() => {
          setDiagnosis(nextDiagnosis);
        });

        if (nextDiagnosis.status === "pending") {
          schedulePoll();
        }
      } catch (error) {
        if (abortController.signal.aborted) {
          return;
        }

        const message =
          error instanceof Error ? error.message : "Diagnosis request failed unexpectedly.";
        logBrowserEvent("error", "diagnosis.sync_failed", {
          error: message,
          path: diagnosisPath,
          request_id:
            error instanceof Error && "requestId" in error ? String(error.requestId) : undefined,
          status:
            error instanceof Error && "status" in error && typeof error.status === "number"
              ? error.status
              : undefined,
        });
        startTransition(() => {
          setDiagnosis(createFailedDiagnosis(message));
        });
      }
    }

    void syncDiagnosis();

    return () => {
      abortController.abort();
      if (pollTimer) {
        window.clearTimeout(pollTimer);
      }
    };
  }, [analysis, diagnosisPath, rerunToken]);

  return (
    <BlockStack gap="500">
      {priorityCard ? <PriorityDetailCard card={priorityCard} /> : null}
      <ShopperJourneyCard analysis={analysis} priorityCard={priorityCard} />
      <DiagnosisCards
        diagnosis={diagnosis}
        onRerun={() => {
          setDiagnosis(createPendingDiagnosis());
          setRerunToken((current) => current + 1);
        }}
      />
    </BlockStack>
  );
}
