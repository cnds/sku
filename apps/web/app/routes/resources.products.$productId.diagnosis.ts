import type { ActionFunctionArgs, LoaderFunctionArgs } from "@remix-run/node";

import { ApiError, createDiagnosis, fetchDiagnosis, parseTimeWindow } from "@/lib/api.server";
import type { ProductSnapshot } from "@/lib/contracts";
import { requestIdFromHeaders } from "@/lib/logging";

export async function loader({ params, request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const requestId = requestIdFromHeaders(request.headers);
  const shopId = url.searchParams.get("shop") ?? "demo.myshopify.com";
  const window = parseTimeWindow(url.searchParams.get("window"));
  const productId = params.productId ?? "";

  try {
    const result = await fetchDiagnosis({ productId, requestId, shopId, window });
    return Response.json(result);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return new Response("Diagnosis not found.", { status: 404 });
    }

    throw error;
  }
}

export async function action({ params, request }: ActionFunctionArgs) {
  const url = new URL(request.url);
  const requestId = requestIdFromHeaders(request.headers);
  const shopId = url.searchParams.get("shop") ?? "demo.myshopify.com";
  const window = parseTimeWindow(url.searchParams.get("window"));
  const productId = params.productId ?? "";
  const snapshot = (await request.json()) as ProductSnapshot;

  const result = await createDiagnosis({ productId, requestId, shopId, snapshot, window });
  return Response.json(result);
}
