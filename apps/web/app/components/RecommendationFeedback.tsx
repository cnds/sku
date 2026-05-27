import { useState } from "react";
import { BlockStack, Button, InlineStack, Text } from "@shopify/polaris";

import type { PriorityBoardType, RecommendationFeedbackAction, TimeWindow } from "@/lib/contracts";

const RECOMMENDATION_FEEDBACK_ROUTE = "/resources/recommendation-feedback";

export const RECOMMENDATION_FEEDBACK_ACTIONS: Array<{
  action: RecommendationFeedbackAction;
  label: string;
}> = [
  { action: "will_try", label: "I will try this" },
  { action: "not_useful", label: "Not useful" },
  { action: "already_fixed", label: "Already fixed" },
  { action: "remind_later", label: "Remind me later" },
];

interface FeedbackFormActionSource {
  action?: unknown;
  getAttribute(name: string): string | null;
}

export function feedbackFormActionUrl(form: FeedbackFormActionSource): string {
  return form.getAttribute("action") ?? RECOMMENDATION_FEEDBACK_ROUTE;
}

interface RecommendationFeedbackSubmission {
  action: RecommendationFeedbackAction;
  board?: PriorityBoardType | "leaker" | "hidden_winner" | null;
  boardDate?: string;
  cardRank?: number;
  context?: Record<string, unknown>;
  productId: string;
  shopId: string;
  window: TimeWindow;
  windowEndDate?: string;
  windowStartDate?: string;
}

export function recommendationFeedbackFormData(submission: RecommendationFeedbackSubmission): FormData {
  const formData = new FormData();
  formData.set("action", submission.action);
  if (submission.board) {
    formData.set("board", submission.board);
  }
  if (submission.boardDate) {
    formData.set("board_date", submission.boardDate);
  }
  if (submission.windowStartDate) {
    formData.set("window_start_date", submission.windowStartDate);
  }
  if (submission.windowEndDate) {
    formData.set("window_end_date", submission.windowEndDate);
  }
  if (typeof submission.cardRank === "number") {
    formData.set("card_rank", String(submission.cardRank));
  }
  if (submission.context && Object.keys(submission.context).length > 0) {
    formData.set("context", JSON.stringify(submission.context));
  }
  formData.set("product_id", submission.productId);
  formData.set("shop_id", submission.shopId);
  formData.set("window", submission.window);
  return formData;
}

export function RecommendationFeedbackButtons({
  board,
  boardDate,
  cardRank,
  context,
  productId,
  shopId,
  window,
  windowEndDate,
  windowStartDate,
}: {
  board?: PriorityBoardType | "leaker" | "hidden_winner" | null;
  boardDate?: string;
  cardRank?: number;
  context?: Record<string, unknown>;
  productId: string;
  shopId: string;
  window: TimeWindow;
  windowEndDate?: string;
  windowStartDate?: string;
}) {
  const [savedAction, setSavedAction] = useState<RecommendationFeedbackAction | null>(null);

  async function handleFeedback(action: RecommendationFeedbackAction) {
    const formData = recommendationFeedbackFormData({
      action,
      board,
      boardDate,
      cardRank,
      context,
      productId,
      shopId,
      window,
      windowEndDate,
      windowStartDate,
    });

    setSavedAction(action);
    await fetch(RECOMMENDATION_FEEDBACK_ROUTE, {
      body: formData,
      method: "POST",
    });
  }

  return (
    <BlockStack gap="100">
      <Text as="p" variant="bodySm" tone="subdued">
        Feedback
      </Text>
      <InlineStack gap="100">
        {RECOMMENDATION_FEEDBACK_ACTIONS.map((item) => (
          <Button key={item.action} onClick={() => void handleFeedback(item.action)} size="slim">
            {item.label}
          </Button>
        ))}
      </InlineStack>
      {savedAction ? (
        <Text as="p" variant="bodySm" tone="subdued">
          Saved: {RECOMMENDATION_FEEDBACK_ACTIONS.find((item) => item.action === savedAction)?.label}
        </Text>
      ) : null}
    </BlockStack>
  );
}
