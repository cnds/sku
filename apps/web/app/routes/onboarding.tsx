import type { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/node";
import { redirect } from "@remix-run/node";
import { Form, useLoaderData, useNavigation } from "@remix-run/react";
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
import {
  cancelBillingPlan,
  changeBillingPlan,
  fetchBillingStatus,
  fetchOnboardingStatus,
  parseTimeWindow,
  subscribeToPlan,
} from "@/lib/api.server";
import type {
  BillingInterval,
  BillingPlan,
  BillingPlanConfigResponse,
  BillingStatusResponse,
  OnboardingChecklistItem,
} from "@/lib/contracts";
import { requestIdFromHeaders } from "@/lib/logging";
import { messages } from "@/lib/messages";
import { hostFromUrl, shopIdFromUrl } from "@/lib/shop";
import { dashboardPath, onboardingPath } from "@/lib/url";

const TRIAL_DAYS = 14;

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const requestId = requestIdFromHeaders(request.headers);
  const shopId = shopIdFromUrl(url);
  const host = hostFromUrl(url);
  const window = parseTimeWindow(url.searchParams.get("window"));
  const [status, billing] = await Promise.all([
    fetchOnboardingStatus({ requestId, shopId, window }),
    fetchBillingStatus({ requestId, shopId }),
  ]);
  return { billing, host, shopId, status, window };
}

export async function action({ request }: ActionFunctionArgs) {
  const url = new URL(request.url);
  const requestId = requestIdFromHeaders(request.headers);
  const host = hostFromUrl(url);
  const window = parseTimeWindow(url.searchParams.get("window"));
  const formData = await request.formData();
  const shopId = stringFromForm(formData.get("shop_id")) || shopIdFromUrl(url);
  const intent = stringFromForm(formData.get("intent")) || "subscribe";

  if (intent === "cancel") {
    await cancelBillingPlan({ requestId, shopId });
    return redirect(onboardingPath(shopId, window, host));
  }

  const plan = billingPlanFromForm(formData.get("plan"));
  const billingInterval = billingIntervalFromForm(formData.get("billing_interval"));
  const result = intent === "change-plan"
    ? await changeBillingPlan({ billingInterval, plan, requestId, shopId })
    : await subscribeToPlan({ billingInterval, plan, requestId, shopId });
  return redirect(result.confirmation_url);
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
  const navigation = useNavigation();
  const health = data.status.integration_health;
  const isSubmitting = navigation.state !== "idle";

  return (
    <Page
      title="SKU Lens setup"
      subtitle={`${data.shopId} · ${formatTimeWindowLabel(data.window)}`}
      backAction={{ content: messages.product.backAction, url: dashboardPath(data.shopId, data.window, data.host) }}
      primaryAction={{
        content: "Open board",
        url: dashboardPath(data.shopId, data.window, data.host),
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

            <PricingSection
              billing={data.billing}
              isSubmitting={isSubmitting}
              shopId={data.shopId}
            />

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

            <BillingManagement billing={data.billing} isSubmitting={isSubmitting} shopId={data.shopId} />
          </BlockStack>
        </Layout.Section>
      </Layout>
    </Page>
  );
}

function PricingSection({
  billing,
  isSubmitting,
  shopId,
}: {
  billing: BillingStatusResponse;
  isSubmitting: boolean;
  shopId: string;
}) {
  return (
    <BlockStack gap="300">
      <InlineStack align="space-between" blockAlign="center" gap="300">
        <BlockStack gap="100">
          <Text as="h2" variant="headingLg">Choose a plan</Text>
          <Text as="p" variant="bodySm" tone="subdued">
            {TRIAL_DAYS}-day trial starts after Shopify confirms the subscription. Daily cards stay included on every paid plan.
          </Text>
        </BlockStack>
        {billing.is_entitled ? <Badge tone="success">Active</Badge> : <Badge tone="attention">Subscription required</Badge>}
      </InlineStack>
      <InlineGrid columns={{ xs: 1, md: 3 }} gap="400">
        {billing.plans.map((plan) => (
          <PlanCard billing={billing} isSubmitting={isSubmitting} key={plan.plan} plan={plan} shopId={shopId} />
        ))}
      </InlineGrid>
    </BlockStack>
  );
}

function PlanCard({
  billing,
  isSubmitting,
  plan,
  shopId,
}: {
  billing: BillingStatusResponse;
  isSubmitting: boolean;
  plan: BillingPlanConfigResponse;
  shopId: string;
}) {
  const isCurrent = billing.current_plan === plan.plan;
  const isPending = billing.pending_plan === plan.plan;
  const intent = billing.is_entitled ? "change-plan" : "subscribe";

  return (
    <Card>
      <BlockStack gap="300">
        <InlineStack align="space-between" blockAlign="center" gap="200">
          <Text as="h3" variant="headingMd">{plan.name}</Text>
          {plan.recommended ? <Badge tone="info">Recommended</Badge> : null}
        </InlineStack>
        <BlockStack gap="100">
          <Text as="p" variant="headingLg">${plan.monthly_price}/mo</Text>
          <Text as="p" variant="bodySm" tone="subdued">
            Annual: ${plan.annual_price_monthly_equivalent}/mo equivalent
          </Text>
        </BlockStack>
        <BlockStack gap="100">
          <Text as="p" variant="bodySm">{plan.ai_refresh_limit.toLocaleString("en-US")} manual AI refreshes / month</Text>
          <Text as="p" variant="bodySm">{plan.pdp_view_soft_limit.toLocaleString("en-US")} PDP views soft limit</Text>
          <Text as="p" variant="bodySm">{plan.history_days} days board history</Text>
        </BlockStack>
        <BlockStack gap="200">
          <PlanSubmitButton
            billing={billing}
            billingInterval="monthly"
            disabled={isSubmitting || (isCurrent && billing.billing_interval === "monthly") || isPending}
            intent={intent}
            label={planButtonLabel({ billing, billingInterval: "monthly", isCurrent, isPending })}
            plan={plan.plan}
            primary={plan.recommended}
            shopId={shopId}
          />
          <PlanSubmitButton
            billing={billing}
            billingInterval="annual"
            disabled={isSubmitting || (isCurrent && billing.billing_interval === "annual") || isPending}
            intent={intent}
            label={planButtonLabel({ billing, billingInterval: "annual", isCurrent, isPending })}
            plan={plan.plan}
            primary={false}
            shopId={shopId}
          />
        </BlockStack>
      </BlockStack>
    </Card>
  );
}

function PlanSubmitButton({
  billing,
  billingInterval,
  disabled,
  intent,
  label,
  plan,
  primary,
  shopId,
}: {
  billing: BillingStatusResponse;
  billingInterval: BillingInterval;
  disabled: boolean;
  intent: string;
  label: string;
  plan: BillingPlan;
  primary: boolean;
  shopId: string;
}) {
  return (
    <Form method="post">
      <input name="shop_id" type="hidden" value={shopId} />
      <input name="plan" type="hidden" value={plan} />
      <input name="billing_interval" type="hidden" value={billingInterval} />
      <input name="intent" type="hidden" value={intent} />
      <Button
        disabled={disabled || (billing.current_plan === plan && billing.billing_interval === billingInterval)}
        fullWidth
        submit
        variant={primary ? "primary" : "secondary"}
      >
        {label}
      </Button>
    </Form>
  );
}

function BillingManagement({
  billing,
  isSubmitting,
  shopId,
}: {
  billing: BillingStatusResponse;
  isSubmitting: boolean;
  shopId: string;
}) {
  const currentPlan = planName(billing, billing.current_plan);
  const pendingPlan = planName(billing, billing.pending_plan);

  return (
    <Card>
      <BlockStack gap="300">
        <InlineStack align="space-between" blockAlign="center" gap="300">
          <Text as="h2" variant="headingMd">Billing</Text>
          <Badge tone={billing.is_entitled ? "success" : "attention"}>{billing.subscription_status}</Badge>
        </InlineStack>
        <InlineGrid columns={{ xs: 1, md: 4 }} gap="300">
          <Metric label="Current plan" value={currentPlan ?? "None"} />
          <Metric label="AI refresh" value={`${billing.ai_refresh.remaining} / ${billing.ai_refresh.limit}`} />
          <Metric label="PDP views" value={`${billing.pdp_views.used.toLocaleString("en-US")} / ${billing.pdp_views.limit.toLocaleString("en-US")}`} />
          <Metric label="Period ends" value={formatDate(billing.current_period_ends_at) ?? "Not active"} />
        </InlineGrid>
        {pendingPlan ? (
          <Banner tone="info">
            <Text as="p" variant="bodyMd">
              Current: {currentPlan ?? "None"}, changes to {pendingPlan} on {formatDate(billing.pending_effective_at) ?? "the next billing cycle"}.
            </Text>
          </Banner>
        ) : null}
        {billing.pdp_views.over_limit ? (
          <Banner tone="warning">
            <Text as="p" variant="bodyMd">
              PDP views are above the plan soft limit. Tracking and board updates continue, but Growth or Pro gives more room.
            </Text>
          </Banner>
        ) : null}
        <Form method="post">
          <input name="shop_id" type="hidden" value={shopId} />
          <input name="intent" type="hidden" value="cancel" />
          <Button disabled={!billing.is_entitled || billing.subscription_status === "cancelled" || isSubmitting} submit>
            Cancel subscription
          </Button>
        </Form>
      </BlockStack>
    </Card>
  );
}

function planButtonLabel({
  billing,
  billingInterval,
  isCurrent,
  isPending,
}: {
  billing: BillingStatusResponse;
  billingInterval: BillingInterval;
  isCurrent: boolean;
  isPending: boolean;
}): string {
  if (isPending) {
    return "Pending change";
  }
  if (isCurrent && billing.billing_interval === billingInterval) {
    return "Current plan";
  }
  if (!billing.is_entitled) {
    return billingInterval === "annual" ? "Start annual trial" : "Start monthly trial";
  }
  return billingInterval === "annual" ? "Switch to annual" : "Switch monthly";
}

function planName(billing: BillingStatusResponse, plan: BillingPlan | null): string | null {
  if (!plan) {
    return null;
  }
  return billing.plans.find((item) => item.plan === plan)?.name ?? plan;
}

function formatDate(value: string | null): string | null {
  if (!value) {
    return null;
  }
  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

function stringFromForm(value: FormDataEntryValue | null): string | null {
  return typeof value === "string" ? value : null;
}

function billingPlanFromForm(value: FormDataEntryValue | null): BillingPlan {
  if (value === "starter" || value === "growth" || value === "pro") {
    return value;
  }
  throw new Response("Invalid billing plan.", { status: 400 });
}

function billingIntervalFromForm(value: FormDataEntryValue | null): BillingInterval {
  if (value === "monthly" || value === "annual") {
    return value;
  }
  throw new Response("Invalid billing interval.", { status: 400 });
}

function Metric({ label, value }: { label: string; value: number | string }) {
  const displayValue = typeof value === "number" ? value.toLocaleString("en-US") : value;
  return (
    <BlockStack gap="050">
      <Text as="p" variant="bodySm" tone="subdued">{label}</Text>
      <Text as="p" variant="headingMd">{displayValue}</Text>
    </BlockStack>
  );
}

export function ErrorBoundary() {
  return (
    <Page title="SKU Lens setup">
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
