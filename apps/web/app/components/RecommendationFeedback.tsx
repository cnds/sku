import type { FormEvent } from "react";
import { useState } from "react";
import { BlockStack, Button, InlineStack, Text } from "@shopify/polaris";

import type { PriorityBoardType, RecommendationFeedbackAction, TimeWindow } from "@/lib/contracts";

export const RECOMMENDATION_FEEDBACK_ACTIONS: Array<{
  action: RecommendationFeedbackAction;
  label: string;
}> = [
  { action: "will_try", label: "I will try this" },
  { action: "not_useful", label: "Not useful" },
  { action: "already_fixed", label: "Already fixed" },
  { action: "remind_later", label: "Remind me later" },
];

export function RecommendationFeedbackButtons({
  board,
  productId,
  shopId,
  window,
}: {
  board?: PriorityBoardType | "leaker" | "hidden_winner" | null;
  productId: string;
  shopId: string;
  window: TimeWindow;
}) {
  const [savedAction, setSavedAction] = useState<RecommendationFeedbackAction | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const action = formData.get("action");
    if (typeof action === "string") {
      setSavedAction(action as RecommendationFeedbackAction);
    }
    await fetch(form.action, {
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
          <form action="/resources/recommendation-feedback" key={item.action} method="post" onSubmit={handleSubmit}>
            <input name="action" type="hidden" value={item.action} />
            {board ? <input name="board" type="hidden" value={board} /> : null}
            <input name="product_id" type="hidden" value={productId} />
            <input name="shop_id" type="hidden" value={shopId} />
            <input name="window" type="hidden" value={window} />
            <Button size="slim" submit>
              {item.label}
            </Button>
          </form>
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
