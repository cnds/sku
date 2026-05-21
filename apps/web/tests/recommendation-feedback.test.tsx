import { renderToStaticMarkup } from "react-dom/server";
import { AppProvider } from "@shopify/polaris";
import polarisTranslations from "@shopify/polaris/locales/en.json";
import { describe, expect, it } from "vitest";

import { RecommendationFeedbackButtons, RECOMMENDATION_FEEDBACK_ACTIONS } from "../app/components/RecommendationFeedback";

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
});
