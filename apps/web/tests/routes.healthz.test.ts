import { describe, expect, it } from "vitest";

import { loader } from "../app/routes/healthz";

describe("healthz route", () => {
  it("returns a minimal ok payload", async () => {
    const response = await loader();

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toContain("application/json");
    await expect(response.json()).resolves.toEqual({ ok: true });
  });
});
