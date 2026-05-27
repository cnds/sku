import { renderToStaticMarkup } from "react-dom/server";
import { AppProvider } from "@shopify/polaris";
import polarisTranslations from "@shopify/polaris/locales/en.json";
import { describe, expect, it } from "vitest";

import {
  RECOMMENDATION_FEEDBACK_ACTIONS,
  RecommendationFeedbackButtons,
  feedbackFormActionUrl,
  recommendationFeedbackFormData,
} from "../app/components/RecommendationFeedback";

describe("recommendation feedback controls", () => {
  it("exposes the four lightweight merchant feedback actions", () => {
    expect(RECOMMENDATION_FEEDBACK_ACTIONS.map((action) => action.label)).toEqual([
      "I will try this",
      "Not useful",
      "Already fixed",
      "Remind me later",
    ]);
  });

  it("renders feedback buttons for a priority card or diagnosis", () => {
    const markup = renderToStaticMarkup(
      <AppProvider i18n={polarisTranslations}>
        <RecommendationFeedbackButtons
          board="leaker"
          productId="product-1"
          shopId="demo.myshopify.com"
          window="24h"
        />
      </AppProvider>,
    );

    expect(markup).toContain("I will try this");
    expect(markup).toContain("Not useful");
    expect(markup).toContain("Already fixed");
    expect(markup).toContain("Remind me later");
  });

  it("uses the form action attribute even when a hidden action field shadows form.action", () => {
    const actionInput = { toString: () => "[object HTMLInputElement]" };

    const actionUrl = feedbackFormActionUrl({
      action: actionInput,
      getAttribute: (name: string) => (name === "action" ? "/resources/recommendation-feedback" : null),
    });

    expect(actionUrl).toBe("/resources/recommendation-feedback");
  });

  it("serializes board window metadata for priority card feedback", () => {
    const formData = recommendationFeedbackFormData({
      action: "will_try",
      board: "leaker",
      boardDate: "2026-05-27",
      cardRank: 1,
      context: { primary_step: "pdp_add_to_cart", surface: "today_priorities" },
      productId: "product-1",
      shopId: "demo.myshopify.com",
      window: "24h",
      windowEndDate: "2026-05-27",
      windowStartDate: "2026-05-26",
    });

    expect(Object.fromEntries(formData.entries())).toEqual({
      action: "will_try",
      board: "leaker",
      board_date: "2026-05-27",
      card_rank: "1",
      context: JSON.stringify({ primary_step: "pdp_add_to_cart", surface: "today_priorities" }),
      product_id: "product-1",
      shop_id: "demo.myshopify.com",
      window: "24h",
      window_end_date: "2026-05-27",
      window_start_date: "2026-05-26",
    });
  });

  it("does not render native feedback forms that can navigate to the resource route", () => {
    const markup = renderToStaticMarkup(
      <AppProvider i18n={polarisTranslations}>
        <RecommendationFeedbackButtons
          board="leaker"
          productId="product-1"
          shopId="demo.myshopify.com"
          window="24h"
        />
      </AppProvider>,
    );

    expect(markup).not.toContain("<form");
    expect(markup).not.toContain('action="/resources/recommendation-feedback"');
  });
});
