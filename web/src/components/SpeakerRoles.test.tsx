import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Job } from "../api/types";
import SpeakerRoles from "./SpeakerRoles";

const job = {
  id: "j1",
  status: "completed",
  speaker_roles: {
    SPEAKER_01: "presenter",
    SPEAKER_02: "presenter",
  },
} as unknown as Job;

function renderRoles(target: Job = job) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SpeakerRoles job={target} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SpeakerRoles", () => {
  it("saves changed roles with PATCH", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ...job,
          speaker_roles: {
            SPEAKER_01: "presenter",
            SPEAKER_02: "feeder",
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderRoles();

    await userEvent.selectOptions(
      screen.getByLabelText("SPEAKER_02"),
      "feeder",
    );
    await userEvent.click(screen.getByRole("button", { name: /save roles/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/jobs/j1/speakers");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "PATCH" });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({
      roles: {
        SPEAKER_01: "presenter",
        SPEAKER_02: "feeder",
      },
    });
    expect(
      await screen.findByText(/cut outputs regenerated/i),
    ).toBeInTheDocument();
  });
});
