# Theme Validation Checklist

Repository fixture coverage currently includes Dawn, Refresh, Sense, Impulse, Prestige, and Debutify.

For each theme:

1. Enable the SKU Lens theme app embed.
2. Confirm the block has the backend ingest endpoint and public token.
3. Open a product page and verify a Pixel `product_view` event.
4. Click product media and verify `media_interaction` plus `product_media` component labeling.
5. Interact with product description/details and verify `product_description` or `product_details`.
6. Change a variant and verify `variant_intent`.
7. Click add to cart and verify Pixel `add_to_cart` plus SDK `buy_box` component intent.
8. Leave the page after dwell time and verify `engage`.
9. Open onboarding status and confirm raw event, PDP view, component, add-to-cart, and checkout completed Pixel coverage.

Live theme validation should be recorded separately from repository fixture tests.
