import type { LoaderFunctionArgs } from "@remix-run/node";
import { isRouteErrorResponse, useLoaderData, useRouteError } from "@remix-run/react";
import { Badge, Banner, InlineStack, Layout, Page, Text } from "@shopify/polaris";

import { AnalysisPanel } from "@/components/AnalysisPanel";
import { formatTimeWindowLabel } from "@/lib/analytics";
import { fetchProductAnalysis, parseTimeWindow } from "@/lib/api.server";
import { requestIdFromHeaders } from "@/lib/logging";
import { messages } from "@/lib/messages";
import { dashboardPath, diagnosisResourcePath } from "@/lib/url";

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
  const shopId = url.searchParams.get("shop") ?? "demo.myshopify.com";
  const window = parseTimeWindow(url.searchParams.get("window"));
  const productId = params.productId ?? "";
  const analysis = await fetchProductAnalysis({ productId, requestId, shopId, window });

  return {
    analysis,
    diagnosisPath: diagnosisResourcePath(productId, shopId, window),
    productId,
    shopId,
    window,
  };
}

export default function ProductAnalysisRoute() {
  const data = useLoaderData<typeof loader>();
  const gapValue = data.analysis.gap;
  const boardType = gapValue > 0 ? "Black Board" : "Red Board";
  const boardTone = gapValue > 0 ? "critical" : "success";

  return (
    <Page
      title={data.productId}
      backAction={{ content: messages.product.backAction, url: dashboardPath(data.shopId, data.window) }}
      titleMetadata={
        <InlineStack gap="200">
          <Badge tone={boardTone}>{boardType}</Badge>
          <Badge>{formatTimeWindowLabel(data.window)}</Badge>
        </InlineStack>
      }
      subtitle={messages.product.subtitle(data.analysis.benchmark_product_id)}
    >
      <Layout>
        <Layout.Section>
          <AnalysisPanel analysis={data.analysis} diagnosisPath={data.diagnosisPath} />
        </Layout.Section>
      </Layout>
    </Page>
  );
}
