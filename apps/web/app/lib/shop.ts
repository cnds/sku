export const DEFAULT_TEST_SHOP_DOMAIN = "sku-dev-uaop8pff.myshopify.com";

export function shopIdFromUrl(url: URL): string {
  return shopIdFromValue(url.searchParams.get("shop"));
}

export function shopIdFromForm(value: FormDataEntryValue | null): string {
  return shopIdFromValue(value);
}

export function hostFromUrl(url: URL): string | undefined {
  const host = url.searchParams.get("host");
  return host && host.length > 0 ? host : undefined;
}

function shopIdFromValue(value: FormDataEntryValue | null): string {
  return typeof value === "string" && value.length > 0 ? value : DEFAULT_TEST_SHOP_DOMAIN;
}
