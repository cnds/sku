import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";
import { Badge, Banner, BlockStack, Button, Card, InlineStack, Layout, Page, Text } from "@shopify/polaris";

import { AnalysisPanel } from "@/components/AnalysisPanel";
import { PageBottomSpacer } from "@/components/PageBottomSpacer";
import { RecommendationFeedbackButtons } from "@/components/RecommendationFeedback";
import { formatTimeWindowLabel } from "@/lib/analytics";
import { fetchBillingStatus, fetchPriorities, fetchProductAnalysis, parseTimeWindow } from "@/lib/api.server";
import { requestIdFromHeaders } from "@/lib/logging";
import { messages } from "@/lib/messages";
import { priorityActionLabel, priorityBoardLabel, priorityTone } from "@/lib/priorities";
import { hostFromUrl, shopIdFromUrl } from "@/lib/shop";
import { dashboardPath, diagnosisResourcePath, onboardingPath } from "@/lib/url";

export function boardLabelForGap(gapValue: number): { label: string; tone: "critical" | "success" } {
  return gapValue > 0
    ? { label: messages.dashboard.blackboardTitle, tone: "critical" }
    : { label: messages.dashboard.redboardTitle, tone: "success" };
}

export function ErrorBoundary() {
  return (
    <Page title={messages.product.errorTitle} backAction={{ content: messages.product.backAction, url: "/" }}>
      <Layout>
        <Layout.Section>
          <Banner tone="critical">
            <Text as="p" variant="bodyMd">{messages.product.errorMessage}</Text>
          </Banner>
        </Layout.Section>
      </Layout>
    </Page>
  );
}

export async function loader({ params, request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const requestId = requestIdFromHeaders(request.headers);
  const shopId = shopIdFromUrl(url);
  const host = hostFromUrl(url);
  const window = parseTimeWindow(url.searchParams.get("window"));
  const productId = params.productId ?? "";
  const billing = await fetchBillingStatus({ requestId, shopId });
  if (!billing.is_entitled) {
    return {
      analysis: null,
      billing,
      diagnosisPath: null,
      host,
      productId,
      priorityCard: null,
      shopId,
      window,
    };
  }

  const [analysis, priorities] = await Promise.all([
    fetchProductAnalysis({ productId, requestId, shopId, window }),
    fetchPriorities({ requestId, shopId, window }),
  ]);
  const priorityCard = priorities.find((card) => card.product_id === productId) ?? null;

  return {
    analysis,
    billing,
    diagnosisPath: diagnosisResourcePath(productId, shopId, window, host),
    host,
    productId,
    priorityCard,
    shopId,
    window,
  };
}

export default function ProductAnalysisRoute() {
  const data = useLoaderData<typeof loader>();
  if (!data.billing.is_entitled || !data.analysis || !data.diagnosisPath) {
    return (
      <Page
        title={data.productId}
        backAction={{ content: messages.product.backAction, url: dashboardPath(data.shopId, data.window, data.host) }}
      >
        <Layout>
          <Layout.Section>
            <BlockStack gap="400">
              <Banner tone="warning">
                <Text as="p" variant="bodyMd">
                  Choose a plan to unlock product diagnostics and manual AI refreshes for {data.shopId}.
                </Text>
              </Banner>
              <Button url={onboardingPath(data.shopId, data.window, data.host)} variant="primary">
                View plans
              </Button>
            </BlockStack>
          </Layout.Section>
        </Layout>
      </Page>
    );
  }

  const board = data.priorityCard
    ? { label: priorityBoardLabel(data.priorityCard.board), tone: priorityTone(data.priorityCard) }
    : boardLabelForGap(data.analysis.gap);
  const feedbackBoard = data.priorityCard?.board ?? (data.analysis.gap > 0 ? "leaker" : "hidden_winner");
  const feedbackContext: Record<string, unknown> = data.priorityCard
    ? {
      primary_step: data.priorityCard.primary_step,
      source_card_rank: data.priorityCard.card_rank,
      surface: "product_detail",
    }
    : {
      benchmark_product_id: data.analysis.benchmark_product_id,
      gap: data.analysis.gap,
      surface: "product_detail",
    };

  return (
    <Page
      title={data.productId}
      backAction={{ content: messages.product.backAction, url: dashboardPath(data.shopId, data.window, data.host) }}
      titleMetadata={
        <InlineStack gap="200">
          <Badge tone={board.tone}>{board.label}</Badge>
          {data.priorityCard ? (
            <Badge tone={priorityTone(data.priorityCard)}>{priorityActionLabel(data.priorityCard)}</Badge>
          ) : null}
          <Badge>{formatTimeWindowLabel(data.window)}</Badge>
        </InlineStack>
      }
      subtitle={messages.product.subtitle(data.analysis.benchmark_product_id)}
    >
      <Layout>
        <Layout.Section>
          <BlockStack gap="400">
            <AnalysisPanel
              aiRefresh={data.billing.ai_refresh}
              analysis={data.analysis}
              diagnosisPath={data.diagnosisPath}
              priorityCard={data.priorityCard}
            />
            <Card>
              <RecommendationFeedbackButtons
                board={feedbackBoard}
                boardDate={data.priorityCard?.board_date}
                cardRank={data.priorityCard?.card_rank}
                context={feedbackContext}
                productId={data.productId}
                shopId={data.shopId}
                window={data.window}
                windowEndDate={data.priorityCard?.window_end_date}
                windowStartDate={data.priorityCard?.window_start_date}
              />
            </Card>
            <PageBottomSpacer />
          </BlockStack>
        </Layout.Section>
      </Layout>
    </Page>
  );
}
