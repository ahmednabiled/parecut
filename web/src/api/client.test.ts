import { describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "./client";

describe("apiFetch", () => {
  it("throws ApiError with the server detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Invalid email or password" }), {
          status: 401,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    await expect(apiFetch("/api/auth/login")).rejects.toMatchObject({
      status: 401,
      message: "Invalid email or password",
    });
    expect(ApiError).toBeDefined();
  });
});
