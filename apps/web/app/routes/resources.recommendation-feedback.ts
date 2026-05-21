import type { ActionFunctionArgs } from "@remix-run/node";

import { parseTimeWindow, postRecommendationFeedback } from "@/lib/api.server";
import type { RecommendationFeedbackAction } from "@/lib/contracts";
import { requestIdFromHeaders } from "@/lib/logging";

const ACTIONS = new Set<RecommendationFeedbackAction>([
  "will_try",
  "not_useful",
  "already_fixed",
  "remind_later",
]);

export async function action({ request }: ActionFunctionArgs) {
  const form = await request.formData();
  const actionValue = String(form.get("action") ?? "");
  if (!ACTIONS.has(actionValue as RecommendationFeedbackAction)) {
    return Response.json({ ok: false }, { status: 422 });
  }

  const response = await postRecommendationFeedback({
    action: actionValue as RecommendationFeedbackAction,
    board: nullableString(form.get("board")),
    productId: String(form.get("product_id") ?? ""),
    requestId: requestIdFromHeaders(request.headers),
    shopId: String(form.get("shop_id") ?? "demo.myshopify.com"),
    window: parseTimeWindow(nullableString(form.get("window"))),
  });
  return Response.json(response);
}

function nullableString(value: FormDataEntryValue | null): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}
