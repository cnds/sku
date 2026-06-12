import type { LoaderFunctionArgs } from "@remix-run/node";
import { useLoaderData } from "@remix-run/react";
import { Badge, Banner, BlockStack, Card, InlineGrid, Layout, Page, Text } from "@shopify/polaris";

import { fetchInternalCardReview, parseTimeWindow } from "@/lib/api.server";
import { requestIdFromHeaders } from "@/lib/logging";
import { messages } from "@/lib/messages";
import { hostFromUrl, shopIdFromUrl } from "@/lib/shop";
import { dashboardPath } from "@/lib/url";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const requestId = requestIdFromHeaders(request.headers);
  const shopId = shopIdFromUrl(url);
  const host = hostFromUrl(url);
  const window = parseTimeWindow(url.searchParams.get("window"));
  const review = await fetchInternalCardReview({ requestId, shopId, window });
  return { host, review, shopId, window };
}

export default function InternalCardReviewRoute() {
  const data = useLoaderData<typeof loader>();

  return (
    <Page
      title="Card review"
      subtitle={`${data.shopId} · ${data.window}`}
      backAction={{ content: messages.product.backAction, url: dashboardPath(data.shopId, data.window, data.host) }}
    >
      <Layout>
        <Layout.Section>
          <BlockStack gap="400">
            {data.review.cards.map((item) => (
              <Card key={`${item.priority_card.board}-${item.priority_card.product_id}`}>
                <BlockStack gap="300">
                  <BlockStack gap="100">
                    <Text as="h2" variant="headingMd">{item.priority_card.product_id}</Text>
                    <Badge>{item.priority_card.board === "hidden_winner" ? "Hidden Winner" : "Leaker"}</Badge>
                  </BlockStack>
                  <InlineGrid columns={{ xs: 1, md: 2 }} gap="400">
                    <ReviewBlock title="Raw events" value={item.raw_event_counts} />
                    <ReviewBlock title="Aggregate evidence" value={item.aggregate_evidence} />
                    <ReviewBlock title="Derived signal" value={item.derived_signal} />
                    <ReviewBlock title="AI summary" value={item.ai_summary} />
                    <ReviewBlock title="Merchant copy" value={item.merchant_copy} />
                  </InlineGrid>
                </BlockStack>
              </Card>
            ))}
            {data.review.cards.length === 0 ? (
              <Banner tone="info">
                <Text as="p" variant="bodyMd">No priority cards are available for review yet.</Text>
              </Banner>
            ) : null}
          </BlockStack>
        </Layout.Section>
      </Layout>
    </Page>
  );
}

function ReviewBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <BlockStack gap="100">
      <Text as="h3" variant="headingSm">{title}</Text>
      <pre style={{ fontSize: 12, lineHeight: 1.5, margin: 0, whiteSpace: "pre-wrap" }}>
        {JSON.stringify(value, null, 2)}
      </pre>
    </BlockStack>
  );
}

export function ErrorBoundary() {
  return (
    <Page title="Card review">
      <Layout>
        <Layout.Section>
          <Banner tone="critical">
            <Text as="p" variant="bodyMd">{messages.errors.unexpectedError}</Text>
          </Banner>
        </Layout.Section>
      </Layout>
    </Page>
  );
}
