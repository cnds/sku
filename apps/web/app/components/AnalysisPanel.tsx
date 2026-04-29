import { startTransition, useEffect, useState } from "react";
import {
  Badge,
  Banner,
  BlockStack,
  Box,
  Card,
  InlineGrid,
  InlineStack,
  SkeletonBodyText,
  Spinner,
  Text,
} from "@shopify/polaris";
import type { DiagnosisResult, ProductAnalysisResult } from "@/lib/contracts";

import { createFailedDiagnosis, createPendingDiagnosis, snapshotFromAnalysis } from "@/lib/diagnosis";
import { REQUEST_ID_HEADER, generateRequestId, logBrowserEvent } from "@/lib/logging";
import { messages } from "@/lib/messages";
import { RadarChart } from "@/components/RadarChart";

interface AnalysisPanelProps {
  analysis: ProductAnalysisResult;
  diagnosisPath: string;
}

const DIAGNOSIS_POLL_INTERVAL_MS = 3_000;

function parseDiagnosisSections(markdown: string | null): { problem: string; cause: string; recommendations: string } {
  if (!markdown) {
    return { problem: messages.analysis.diagnosisNoReport, cause: "", recommendations: "" };
  }

  const sections = markdown.split(/^##\s+/m).filter(Boolean);

  if (sections.length >= 3) {
    return {
      problem: sections[0].replace(/^[^\n]*\n/, "").trim(),
      cause: sections[1].replace(/^[^\n]*\n/, "").trim(),
      recommendations: sections[2].replace(/^[^\n]*\n/, "").trim(),
    };
  }

  const paragraphs = markdown.split(/\n\n+/).filter((p) => p.trim());
  if (paragraphs.length >= 3) {
    return {
      problem: paragraphs[0].trim(),
      cause: paragraphs[1].trim(),
      recommendations: paragraphs.slice(2).join("\n\n").trim(),
    };
  }

  return { problem: markdown.trim(), cause: "", recommendations: "" };
}

function DiagnosisCards({ diagnosis }: { diagnosis: DiagnosisResult }) {
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

  const { problem, cause, recommendations } = parseDiagnosisSections(diagnosis.report_markdown);

  const cards: Array<{ title: string; content: string; toneColor: string; bgColor: string; borderColor: string }> = [
    {
      title: messages.analysis.cardProblem,
      content: problem,
      toneColor: "#d48806",
      bgColor: "#fffbe6",
      borderColor: "#ffe58f",
    },
    {
      title: messages.analysis.cardCause,
      content: cause,
      toneColor: "#333333",
      bgColor: "#fafafa",
      borderColor: "#d9d9d9",
    },
    {
      title: messages.analysis.cardRecommendations,
      content: recommendations,
      toneColor: "#389e0d",
      bgColor: "#f6ffed",
      borderColor: "#b7eb8f",
    },
  ];

  return (
    <Box>
      <Box paddingBlockEnd="300">
        <InlineStack gap="200" blockAlign="center">
          <Text as="h2" variant="headingMd">{messages.analysis.diagnosisHeading}</Text>
          <Badge tone="success">{messages.analysis.diagnosisReady}</Badge>
        </InlineStack>
      </Box>
      <InlineGrid columns={{ xs: 1, md: 3 }} gap="400">
        {cards.map((card) => (
          <div
            key={card.title}
            style={{
              border: `1px solid ${card.borderColor}`,
              borderRadius: 8,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                background: card.bgColor,
                padding: "10px 14px",
                fontWeight: "bold",
                color: card.toneColor,
                fontSize: 13,
              }}
            >
              {card.title}
            </div>
            <div style={{ padding: 14, fontSize: 13, color: "#444", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
              {card.content || "—"}
            </div>
          </div>
        ))}
      </InlineGrid>
    </Box>
  );
}

export function AnalysisPanel({ analysis, diagnosisPath }: AnalysisPanelProps) {
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult>(createPendingDiagnosis);

  useEffect(() => {
    const abortController = new AbortController();
    let pollTimer: number | undefined;

    async function fetchDiagnosis(init?: RequestInit): Promise<DiagnosisResult> {
      const requestId = generateRequestId();
      const headers = new Headers(init?.headers);
      headers.set(REQUEST_ID_HEADER, requestId);
      const response = await fetch(diagnosisPath, {
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
  }, [analysis, diagnosisPath]);

  return (
    <BlockStack gap="500">
      <Card>
        <RadarChart
          target={analysis.funnel.target}
          benchmark={analysis.funnel.benchmark}
          componentComparisons={analysis.component_comparisons}
        />
      </Card>

      <DiagnosisCards diagnosis={diagnosis} />
    </BlockStack>
  );
}
