import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import Settings from "./Settings";

const PROFILE_PAYLOAD = {
  user: {
    id: "u1",
    email: "demo@parecut.app",
    full_name: "Demo Editor",
    avatar_url: null,
    created_at: "2026-01-01T00:00:00Z",
  },
  profile: {
    credit_balance_minutes: 30,
    default_fps: "25",
    default_enhance_mix: 80,
    default_silence_pad_ms: 150,
  },
  jobs: [],
  ledger: [],
};

function renderSettings() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Settings />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Settings", () => {
  it("shows a retryable error alert when loading profile fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Server unavailable" }), {
          status: 500,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    renderSettings();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /could not load your settings/i,
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("enables saving only when dirty and persists updates", async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...PROFILE_PAYLOAD,
              user: { ...PROFILE_PAYLOAD.user, full_name: "Ada Lovelace" },
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify(PROFILE_PAYLOAD), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    renderSettings();

    const nameInput = await screen.findByDisplayValue("Demo Editor");

    const saveButton = screen.getByRole("button", { name: /save settings/i });
    expect(saveButton).toBeDisabled();

    await user.clear(nameInput);
    await user.type(nameInput, "Ada Lovelace");
    expect(saveButton).toBeEnabled();

    await user.click(saveButton);
    expect(await screen.findByRole("status")).toHaveTextContent("Settings saved.");
    expect(saveButton).toBeDisabled();
  });
});
