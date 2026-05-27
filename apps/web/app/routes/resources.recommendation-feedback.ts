import type { ActionFunctionArgs } from "@remix-run/node";

import { parseTimeWindow, postRecommendationFeedback } from "@/lib/api.server";
import type { RecommendationFeedbackAction } from "@/lib/contracts";
import { requestIdFromHeaders } from "@/lib/logging";
import { shopIdFromForm } from "@/lib/shop";

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
    boardDate: nullableString(form.get("board_date")),
    cardRank: nullableNumber(form.get("card_rank")),
    context: parseContext(form.get("context")),
    productId: String(form.get("product_id") ?? ""),
    requestId: requestIdFromHeaders(request.headers),
    shopId: shopIdFromForm(form.get("shop_id")),
    window: parseTimeWindow(nullableString(form.get("window"))),
    windowEndDate: nullableString(form.get("window_end_date")),
    windowStartDate: nullableString(form.get("window_start_date")),
  });
  return Response.json(response);
}

function nullableString(value: FormDataEntryValue | null): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function nullableNumber(value: FormDataEntryValue | null): number | null {
  const stringValue = nullableString(value);
  if (stringValue === null) {
    return null;
  }
  const numberValue = Number.parseInt(stringValue, 10);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function parseContext(value: FormDataEntryValue | null): Record<string, unknown> | null {
  const stringValue = nullableString(value);
  if (stringValue === null) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(stringValue);
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
}
