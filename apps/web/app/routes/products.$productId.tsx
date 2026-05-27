import type { LoaderFunctionArgs } from "@remix-run/node";
import { isRouteErrorResponse, useLoaderData, useRouteError } from "@remix-run/react";
import { Badge, Banner, BlockStack, Card, InlineStack, Layout, Page, Text } from "@shopify/polaris";

import { AnalysisPanel } from "@/components/AnalysisPanel";
import { RecommendationFeedbackButtons } from "@/components/RecommendationFeedback";
import { formatTimeWindowLabel } from "@/lib/analytics";
import { fetchProductAnalysis, parseTimeWindow } from "@/lib/api.server";
import { requestIdFromHeaders } from "@/lib/logging";
import { messages } from "@/lib/messages";
import { hostFromUrl, shopIdFromUrl } from "@/lib/shop";
import { dashboardPath, diagnosisResourcePath } from "@/lib/url";

export function boardLabelForGap(gapValue: number): { label: string; tone: "critical" | "success" } {
  return gapValue > 0
    ? { label: messages.dashboard.blackboardTitle, tone: "critical" }
    : { label: messages.dashboard.redboardTitle, tone: "success" };
}

export function ErrorBoundary() {
  const error = useRouteError();

  let message: string = messages.product.errorMessage;
  if (isRouteErrorResponse(error)) {
    message = error.status === 404
      ? messages.product.notFound
      : (typeof error.data === "string" ? error.data : message);
  } else if (error instanceof Error) {
    message = error.message;
  }

  return (
    <Page title={messages.product.errorTitle} backAction={{ content: messages.product.backAction, url: "/" }}>
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

export async function loader({ params, request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const requestId = requestIdFromHeaders(request.headers);
  const shopId = shopIdFromUrl(url);
  const host = hostFromUrl(url);
  const window = parseTimeWindow(url.searchParams.get("window"));
  const productId = params.productId ?? "";
  const analysis = await fetchProductAnalysis({ productId, requestId, shopId, window });

  return {
    analysis,
    diagnosisPath: diagnosisResourcePath(productId, shopId, window, host),
    host,
    productId,
    shopId,
    window,
  };
}

export default function ProductAnalysisRoute() {
  const data = useLoaderData<typeof loader>();
  const board = boardLabelForGap(data.analysis.gap);

  return (
    <Page
      title={data.productId}
      backAction={{ content: messages.product.backAction, url: dashboardPath(data.shopId, data.window, data.host) }}
      titleMetadata={
        <InlineStack gap="200">
          <Badge tone={board.tone}>{board.label}</Badge>
          <Badge>{formatTimeWindowLabel(data.window)}</Badge>
        </InlineStack>
      }
      subtitle={messages.product.subtitle(data.analysis.benchmark_product_id)}
    >
      <Layout>
        <Layout.Section>
          <BlockStack gap="400">
            <AnalysisPanel analysis={data.analysis} diagnosisPath={data.diagnosisPath} />
            <Card>
              <RecommendationFeedbackButtons
                board={data.analysis.gap > 0 ? "leaker" : "hidden_winner"}
                context={{
                  benchmark_product_id: data.analysis.benchmark_product_id,
                  gap: data.analysis.gap,
                  surface: "product_detail",
                }}
                productId={data.productId}
                shopId={data.shopId}
                window={data.window}
              />
            </Card>
          </BlockStack>
        </Layout.Section>
      </Layout>
    </Page>
  );
}
