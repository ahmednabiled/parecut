import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard";

const PROFILE_PAYLOAD = {
  user: {
    id: "u1",
    email: "demo@parecut.app",
    full_name: "Demo Editor",
    avatar_url: null,
    created_at: "2026-01-01T00:00:00Z",
  },
  profile: {
    credit_balance_minutes: 24.5,
    default_fps: "25",
    default_enhance_mix: 80,
    default_silence_pad_ms: 150,
  },
  jobs: [
    {
      id: "j1",
      parent_job_id: null,
      effect: null,
      source_filename: "podcast_ep12.wav",
      fps: "25",
      duration_seconds: 180,
      sample_rate: 48000,
      status: "completed",
      current_stage: "completed",
      error_code: null,
      speaker_roles: {},
      pipeline_config: {
        denoise: true,
        enhance: true,
        enhance_mix: 80,
        separate_music: false,
        separate_speakers: false,
        transcribe: true,
        rough_cut: true,
        silence_pad_ms: 150,
        studio_chain: null,
        transcription_languages: ["en"],
      },
      artifacts: [
        {
          id: "a1",
          kind: "enhanced",
          format: "wav",
          download_url: "/a1",
          size_bytes: 1024,
        },
      ],
      created_at: "2026-01-01T10:00:00Z",
      updated_at: "2026-01-01T10:05:00Z",
    },
    {
      id: "j2",
      parent_job_id: null,
      effect: null,
      source_filename: "documentary_broll.mp4",
      fps: "24",
      duration_seconds: 95,
      sample_rate: 48000,
      status: "failed",
      current_stage: "failed",
      error_code: "ERR",
      speaker_roles: {},
      pipeline_config: {
        denoise: true,
        enhance: false,
        enhance_mix: 80,
        separate_music: false,
        separate_speakers: false,
        transcribe: false,
        rough_cut: false,
        silence_pad_ms: 150,
        studio_chain: null,
        transcription_languages: ["en"],
      },
      artifacts: [],
      created_at: "2026-01-02T10:00:00Z",
      updated_at: "2026-01-02T10:02:00Z",
    },
  ],
  ledger: [],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Dashboard", () => {
  it("filters projects by filename and status, and clears filters", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(PROFILE_PAYLOAD), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("podcast_ep12.wav")).toBeInTheDocument();
    expect(screen.getByText("documentary_broll.mp4")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /failed/i }));
    expect(screen.queryByText("podcast_ep12.wav")).not.toBeInTheDocument();
    expect(screen.getByText("documentary_broll.mp4")).toBeInTheDocument();

    await userEvent.type(
      screen.getByLabelText(/filter projects by filename/i),
      "nonexistent",
    );
    expect(
      screen.getByText(/no projects match your current filter/i),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: /clear filters/i }),
    );
    expect(screen.getByText("podcast_ep12.wav")).toBeInTheDocument();
    expect(screen.getByText("documentary_broll.mp4")).toBeInTheDocument();
  });
});
