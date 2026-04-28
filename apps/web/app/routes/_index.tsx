import { useCallback, useMemo } from "react";
import type { LoaderFunctionArgs } from "@remix-run/node";
import { isRouteErrorResponse, useLoaderData, useNavigate, useRouteError } from "@remix-run/react";
import {
  Banner,
  BlockStack,
  Box,
  Divider,
  InlineGrid,
  Layout,
  Page,
  Tabs,
  Text,
} from "@shopify/polaris";

import { LeaderboardTable } from "@/components/LeaderboardTable";
import { TIME_WINDOWS, formatTimeWindowLabel } from "@/lib/analytics";
import { fetchLeaderboard, parseTimeWindow } from "@/lib/api.server";
import { messages } from "@/lib/messages";
import { dashboardPath, productPath } from "@/lib/url";

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const shopId = url.searchParams.get("shop") ?? "demo.myshopify.com";
  const window = parseTimeWindow(url.searchParams.get("window"));
  const [blackboard, redboard] = await Promise.all([
    fetchLeaderboard({ board: "black", shopId, window }),
    fetchLeaderboard({ board: "red", shopId, window }),
  ]);

  return { blackboard, redboard, shopId, window };
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

  return (
    <Page
      title={messages.app.name}
      subtitle={messages.dashboard.subtitle}
      primaryAction={{
        content: messages.dashboard.viewTopProduct,
        url: data.blackboard[0]
          ? productPath(data.blackboard[0].product_id, data.shopId, data.window)
          : undefined,
        disabled: data.blackboard.length === 0,
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
                  <InlineGrid columns={{ xs: 1, md: 2 }} gap="400">
                    <StatCard
                      label={messages.dashboard.statUnderperformers}
                      value={data.blackboard.length}
                      description={messages.dashboard.statUnderperformersDesc}
                    />
                    <StatCard
                      label={messages.dashboard.statHiddenGems}
                      value={data.redboard.length}
                      description={messages.dashboard.statHiddenGemsDesc}
                    />
                  </InlineGrid>

                  <Divider />

                  <LeaderboardTable
                    rows={data.blackboard}
                    shopId={data.shopId}
                    title={messages.dashboard.blackboardTitle}
                    tone="critical"
                    window={data.window}
                  />

                  <LeaderboardTable
                    rows={data.redboard}
                    shopId={data.shopId}
                    title={messages.dashboard.redboardTitle}
                    tone="success"
                    window={data.window}
                  />
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

function StatCard({
  label,
  value,
  description,
}: {
  label: string;
  value: number;
  description: string;
}) {
  return (
    <Box
      background="bg-surface"
      borderRadius="300"
      borderWidth="025"
      borderColor="border"
      padding="400"
    >
      <BlockStack gap="100">
        <Text as="p" variant="bodySm" tone="subdued">
          {label}
        </Text>
        <Text as="p" variant="headingXl">
          {value}
        </Text>
        <Text as="p" variant="bodySm" tone="subdued">
          {description}
        </Text>
      </BlockStack>
    </Box>
  );
}
