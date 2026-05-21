# Theme Validation Checklist

Repository fixture coverage currently includes Dawn, Refresh, Sense, Impulse, Prestige, and Debutify.

For each theme:

1. Enable the SKU Lens theme app embed.
2. Confirm the block has the backend ingest endpoint and public token.
3. Open a product page and verify a `view` event.
4. Click product media and verify `media` plus `product_media` component labeling.
5. Interact with product description/details and verify `product_description` or `product_details`.
6. Change a variant and verify `variant`.
7. Click add to cart and verify `add_to_cart` plus `buy_box`.
8. Leave the page after dwell time and verify `engage`.
9. Open onboarding status and confirm raw event, PDP view, component, and add-to-cart coverage.

Live theme validation should be recorded separately from repository fixture tests.
