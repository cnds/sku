function routeParams(shopId: string, window: string, host?: string): URLSearchParams {
  const params = new URLSearchParams({ shop: shopId, window });
  if (host) {
    params.set("host", host);
  }
  return params;
}

export function productPath(productId: string, shopId: string, window: string, host?: string): string {
  const params = routeParams(shopId, window, host);
  return `/products/${encodeURIComponent(productId)}?${params}`;
}

export function dashboardPath(shopId: string, window: string, host?: string): string {
  const params = routeParams(shopId, window, host);
  return `/?${params}`;
}

export function diagnosisResourcePath(productId: string, shopId: string, window: string, host?: string): string {
  const params = routeParams(shopId, window, host);
  return `/resources/products/${encodeURIComponent(productId)}/diagnosis?${params}`;
}
