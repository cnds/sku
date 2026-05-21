import type { LoaderFunctionArgs } from "@remix-run/node";
import { isRouteErrorResponse, useLoaderData, useRouteError } from "@remix-run/react";
import {
  Badge,
  Banner,
  BlockStack,
  Button,
  Card,
  InlineGrid,
  InlineStack,
  Layout,
  Page,
  Text,
} from "@shopify/polaris";

import { formatTimeWindowLabel } from "@/lib/analytics";
import { fetchOnboardingStatus, parseTimeWindow } from "@/lib/api.server";
import type { OnboardingChecklistItem } from "@/lib/contracts";
import { requestIdFromHeaders } from "@/lib/logging";
import { messages } from "@/lib/messages";
import { dashboardPath } from "@/lib/url";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const requestId = requestIdFromHeaders(request.headers);
  const shopId = url.searchParams.get("shop") ?? "demo.myshopify.com";
  const window = parseTimeWindow(url.searchParams.get("window"));
  const status = await fetchOnboardingStatus({ requestId, shopId, window });
  return { shopId, status, window };
}

function checklistTone(item: OnboardingChecklistItem): "attention" | "info" | "success" {
  if (item.status === "done") return "success";
  if (item.status === "action") return "attention";
  return "info";
}

function statusLabel(item: OnboardingChecklistItem): string {
  if (item.status === "done") return "Done";
  if (item.status === "action") return "Action";
  return "Waiting";
}

export default function OnboardingRoute() {
  const data = useLoaderData<typeof loader>();
  const health = data.status.integration_health;

  return (
    <Page
      title="SKU Lens setup"
      subtitle={`${data.shopId} · ${formatTimeWindowLabel(data.window)}`}
      backAction={{ content: messages.product.backAction, url: dashboardPath(data.shopId, data.window) }}
      primaryAction={{
        content: "Open board",
        url: dashboardPath(data.shopId, data.window),
      }}
    >
      <Layout>
        <Layout.Section>
          <BlockStack gap="400">
            <Banner tone={data.status.installed ? "info" : "warning"}>
              <Text as="p" variant="bodyMd">
                {data.status.installed
                  ? "Install is connected. Enable the theme app embed and wait for raw storefront events before expecting priority cards."
                  : "No installation record yet. Start the Shopify install flow, then return here to activate tracking."}
              </Text>
            </Banner>

            <InlineGrid columns={{ xs: 1, md: 3 }} gap="400">
              <Card>
                <BlockStack gap="200">
                  <Text as="h2" variant="headingMd">Theme app embed</Text>
                  <Text as="p" variant="bodySm" tone="subdued">
                    Activate the embed, then open a product page to send the first event.
                  </Text>
                  <Button url={data.status.app_embed_deep_link} external>
                    Open theme editor
                  </Button>
                </BlockStack>
              </Card>
              <Card>
                <BlockStack gap="200">
                  <Text as="h2" variant="headingMd">Public token</Text>
                  <Text as="p" variant="bodySm" tone="subdued">
                    {data.status.public_token ?? "Available after Shopify install completes."}
                  </Text>
                </BlockStack>
              </Card>
              <Card>
                <BlockStack gap="200">
                  <Text as="h2" variant="headingMd">Ingest endpoint</Text>
                  <Text as="p" variant="bodySm" tone="subdued">
                    {data.status.ingest_endpoint}
                  </Text>
                </BlockStack>
              </Card>
            </InlineGrid>

            <Card>
              <BlockStack gap="300">
                <InlineStack align="space-between" blockAlign="center">
                  <Text as="h2" variant="headingMd">Tracking status</Text>
                  <Badge tone={health.status === "healthy" ? "success" : "attention"}>
                    {health.status.replace("_", " ")}
                  </Badge>
                </InlineStack>
                <Text as="p" variant="bodySm" tone="subdued">
                  Last raw event: {data.status.last_raw_event_at ?? "not seen yet"}
                </Text>
                <InlineGrid columns={{ xs: 2, md: 6 }} gap="300">
                  <Metric label="PDP views" value={health.coverage.views} />
                  <Metric label="Components" value={health.coverage.component_clicks} />
                  <Metric label="Add-to-cart" value={health.coverage.add_to_carts} />
                  <Metric label="Orders" value={health.coverage.orders} />
                  <Metric label="Impressions" value={health.coverage.impressions} />
                  <Metric label="Clicks" value={health.coverage.clicks} />
                </InlineGrid>
              </BlockStack>
            </Card>

            <Card>
              <BlockStack gap="300">
                <Text as="h2" variant="headingMd">Setup checklist</Text>
                <BlockStack gap="200">
                  {data.status.checklist.map((item) => (
                    <InlineStack align="space-between" blockAlign="start" gap="300" key={item.key}>
                      <BlockStack gap="050">
                        <Text as="p" variant="bodyMd" fontWeight="semibold">{item.label}</Text>
                        <Text as="p" variant="bodySm" tone="subdued">{item.message}</Text>
                      </BlockStack>
                      <Badge tone={checklistTone(item)}>{statusLabel(item)}</Badge>
                    </InlineStack>
                  ))}
                </BlockStack>
              </BlockStack>
            </Card>
          </BlockStack>
        </Layout.Section>
      </Layout>
    </Page>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <BlockStack gap="050">
      <Text as="p" variant="bodySm" tone="subdued">{label}</Text>
      <Text as="p" variant="headingMd">{value.toLocaleString("en-US")}</Text>
    </BlockStack>
  );
}

export function ErrorBoundary() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? (typeof error.data === "string" ? error.data : messages.errors.unexpectedError)
    : error instanceof Error
      ? error.message
      : messages.errors.unexpectedError;

  return (
    <Page title="SKU Lens setup">
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
