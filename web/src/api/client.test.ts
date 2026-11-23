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

  it("keeps the 402 shortfall payload for inline handling", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "Insufficient credits",
            required_minutes: 3,
            available_minutes: 1,
          }),
          {
            status: 402,
            headers: { "content-type": "application/json" },
          },
        ),
      ),
    );

    await expect(apiFetch("/api/jobs")).rejects.toMatchObject({
      status: 402,
      message: "Insufficient credits",
      payload: { required_minutes: 3, available_minutes: 1 },
    });
  });

  it("extracts readable validation messages from FastAPI 422 detail arrays", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: [
              {
                loc: ["body", "password"],
                msg: "Value error, Password must be at least 8 characters",
              },
            ],
          }),
          {
            status: 422,
            headers: { "content-type": "application/json" },
          },
        ),
      ),
    );

    await expect(apiFetch("/api/auth/register")).rejects.toMatchObject({
      status: 422,
      message: "Password must be at least 8 characters",
    });
  });

  it("does not force application/json content-type for FormData bodies", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const form = new FormData();
    form.append("name", "clip");
    await apiFetch("/api/upload", { method: "POST", body: form });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;
    expect(headers.has("content-type")).toBe(false);
  });
});
