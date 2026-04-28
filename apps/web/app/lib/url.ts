export function productPath(productId: string, shopId: string, window: string): string {
  const params = new URLSearchParams({ shop: shopId, window });
  return `/products/${encodeURIComponent(productId)}?${params}`;
}

export function dashboardPath(shopId: string, window: string): string {
  const params = new URLSearchParams({ shop: shopId, window });
  return `/?${params}`;
}

export function diagnosisResourcePath(productId: string, shopId: string, window: string): string {
  const params = new URLSearchParams({ shop: shopId, window });
  return `/resources/products/${encodeURIComponent(productId)}/diagnosis?${params}`;
}
