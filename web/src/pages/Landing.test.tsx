import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth/AuthProvider";
import Landing from "./Landing";

function renderLanding(meResponse: Response) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(meResponse));
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <MemoryRouter>
          <Landing />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Landing", () => {
  it("renders the hero and interactive signal flow map for visitors", async () => {
    renderLanding(
      new Response(JSON.stringify({ detail: "Not authenticated" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );

    expect(
      screen.getByRole("heading", { name: /raw audio in/i }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: /^start free$/i }),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /01 restore/i }));
    expect(
      screen.getByText(/strip room noise and finish dialogue to -16 lufs/i),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: /03 transcribe & cut/i }),
    );
    expect(
      screen.getByText(/align english\/arabic speech/i),
    ).toBeInTheDocument();
  });

  it("shows Open dashboard when the user is signed in", async () => {
    renderLanding(
      new Response(
        JSON.stringify({
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
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const dashboardLinks = await screen.findAllByRole("link", {
      name: /open dashboard/i,
    });
    expect(dashboardLinks.length).toBeGreaterThan(0);
  });
});
