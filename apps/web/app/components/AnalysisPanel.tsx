import { startTransition, useEffect, useState } from "react";
import {
  Badge,
  Banner,
  BlockStack,
  Box,
  Card,
  DataTable,
  Divider,
  InlineGrid,
  InlineStack,
  SkeletonBodyText,
  Spinner,
  Text,
} from "@shopify/polaris";
import type { DiagnosisResult, ProductAnalysisResult } from "@/lib/contracts";

import { COMPONENT_LABELS } from "@/lib/analytics";
import { createFailedDiagnosis, createPendingDiagnosis, snapshotFromAnalysis } from "@/lib/diagnosis";
import { messages } from "@/lib/messages";

interface AnalysisPanelProps {
  analysis: ProductAnalysisResult;
  diagnosisPath: string;
}

const DIAGNOSIS_POLL_INTERVAL_MS = 3_000;

function MetricCard({ label, target, benchmark }: { label: string; target: number; benchmark: number }) {
  const diff = target - benchmark;
  const isPositive = diff >= 0;

  return (
    <Box
      background="bg-surface"
      borderRadius="300"
      borderWidth="025"
      borderColor="border"
      padding="400"
    >
      <BlockStack gap="200">
        <Text as="p" variant="bodySm" tone="subdued">
          {label}
        </Text>
        <InlineStack gap="200" blockAlign="baseline">
          <Text as="p" variant="headingXl">
            {target.toLocaleString()}
          </Text>
          <Text as="p" variant="bodySm" tone="subdued">
            {messages.analysis.metricVs(benchmark.toLocaleString())}
          </Text>
        </InlineStack>
        <Badge tone={isPositive ? "success" : "critical"}>
          {`${isPositive ? "+" : ""}${diff.toLocaleString()}`}
        </Badge>
      </BlockStack>
    </Box>
  );
}

function DiagnosisPanel({ diagnosis }: { diagnosis: DiagnosisResult }) {
  if (diagnosis.status === "pending") {
    return (
      <Card>
        <BlockStack gap="400">
          <InlineStack gap="200" blockAlign="center">
            <Spinner size="small" />
            <Text as="h2" variant="headingMd">
              {messages.analysis.diagnosisHeading}
            </Text>
            <Badge tone="attention">{messages.analysis.diagnosisGenerating}</Badge>
          </InlineStack>
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
          <InlineStack gap="200" blockAlign="center">
            <Text as="h2" variant="headingMd">
              {messages.analysis.diagnosisHeading}
            </Text>
            <Badge tone="critical">{messages.analysis.diagnosisFailed}</Badge>
          </InlineStack>
          <Banner tone="critical">
            {diagnosis.report_markdown ?? messages.analysis.diagnosisFailedFallback}
          </Banner>
        </BlockStack>
      </Card>
    );
  }

  return (
    <Card>
      <BlockStack gap="300">
        <InlineStack gap="200" blockAlign="center">
          <Text as="h2" variant="headingMd">
            {messages.analysis.diagnosisHeading}
          </Text>
          <Badge tone="success">{messages.analysis.diagnosisReady}</Badge>
        </InlineStack>
        <Divider />
        <Box>
          <Text as="span" variant="bodyMd">
            <span style={{ whiteSpace: "pre-wrap" }}>
              {diagnosis.report_markdown ?? messages.analysis.diagnosisNoReport}
            </span>
          </Text>
        </Box>
      </BlockStack>
    </Card>
  );
}

export function AnalysisPanel({ analysis, diagnosisPath }: AnalysisPanelProps) {
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult>(createPendingDiagnosis);

  useEffect(() => {
    const abortController = new AbortController();
    let pollTimer: number | undefined;

    async function fetchDiagnosis(init?: RequestInit): Promise<DiagnosisResult> {
      const response = await fetch(diagnosisPath, {
        ...init,
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
        throw new Error(`Diagnosis request failed with status ${response.status}.`);
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
        const nextDiagnosis = await fetchDiagnosis();
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
  }, [analysis, diagnosisPath]);

  const { target, benchmark } = analysis.funnel;

  return (
    <BlockStack gap="500">
      <Card>
        <BlockStack gap="400">
          <InlineStack align="space-between" blockAlign="center">
            <Text as="h2" variant="headingMd">
              {messages.analysis.funnelHeading}
            </Text>
            <Text as="p" variant="bodySm" tone="subdued">
              {messages.analysis.benchmarkLabel(analysis.benchmark_product_id)}
            </Text>
          </InlineStack>
          <InlineGrid columns={{ xs: 1, md: 3 }} gap="400">
            <MetricCard label={messages.analysis.metricViews} target={target.views} benchmark={benchmark.views} />
            <MetricCard label={messages.analysis.metricAddToCart} target={target.add_to_carts} benchmark={benchmark.add_to_carts} />
            <MetricCard label={messages.analysis.metricOrders} target={target.orders} benchmark={benchmark.orders} />
          </InlineGrid>
        </BlockStack>
      </Card>

      <DiagnosisPanel diagnosis={diagnosis} />

      <Card>
        <BlockStack gap="300">
          <Text as="h2" variant="headingMd">
            {messages.analysis.componentHeading}
          </Text>
          <Text as="p" variant="bodySm" tone="subdued">
            {messages.analysis.componentDescription}
          </Text>
          <DataTable
            columnContentTypes={["text", "numeric", "numeric", "numeric"]}
            headings={[messages.analysis.componentColumnName, messages.analysis.componentColumnTargetCtr, messages.analysis.componentColumnBenchmarkCtr, messages.analysis.componentColumnDelta]}
            rows={analysis.component_comparisons.map((component) => [
              COMPONENT_LABELS[component.component_id] ?? component.component_id,
              `${(component.target_ctr * 100).toFixed(1)}%`,
              `${(component.benchmark_ctr * 100).toFixed(1)}%`,
              `${(component.delta * 100).toFixed(1)}%`,
            ])}
          />
        </BlockStack>
      </Card>
    </BlockStack>
  );
}
