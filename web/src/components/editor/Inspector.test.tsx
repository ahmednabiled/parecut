import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DEFAULT_STUDIO } from "../../lib/effects";
import Inspector from "./Inspector";

function renderInspector(onApply = vi.fn()) {
  render(
    <Inspector
      effects={[]}
      applying={null}
      onApply={onApply}
      inputLabel="Original audio"
      error={null}
      shortfall={null}
      transcriptJob={null}
      speakerJob={null}
      onSpeakerUpdated={() => {}}
      defaultMix={0.8}
      defaultStudio={DEFAULT_STUDIO}
      defaultLanguages={["en"]}
      defaultAudioFormat="mp3"
      defaultDialect="auto"
    />,
  );
  return onApply;
}

describe("Inspector audio output", () => {
  it("defaults to standard mp3", () => {
    renderInspector();
    expect(
      screen.getByRole("button", { name: "Standard (MP3)" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("sends lossless wav with the applied effect", async () => {
    const onApply = renderInspector();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Lossless (WAV)" }));
    await user.click(screen.getByRole("button", { name: "Apply enhancement" }));

    const args = onApply.mock.calls[0];
    expect(args[0]).toBe("enhance");
    expect(args[4]).toBe("wav");
  });

  it("toggles transcription languages with pressed buttons", async () => {
    const onApply = renderInspector();
    const user = userEvent.setup();

    const arabic = screen.getByRole("button", { name: "Arabic" });
    expect(arabic).toHaveAttribute("aria-pressed", "false");

    await user.click(arabic);
    expect(arabic).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Transcribe" }));

    const args = onApply.mock.calls[0];
    expect(args[0]).toBe("transcribe");
    expect(args[3]).toEqual(["en", "ar"]);
  });

  it("sends the selected Arabic dialect with transcription", async () => {
    const onApply = renderInspector();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Arabic" }));
    const egyptian = screen.getByRole("button", { name: "Egyptian" });
    expect(egyptian).toHaveAttribute("aria-pressed", "false");

    await user.click(egyptian);
    expect(egyptian).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Transcribe" }));

    const args = onApply.mock.calls[0];
    expect(args[0]).toBe("transcribe");
    expect(args[5]).toBe("egyptian");
  });

  it("links raw transcript_before SRT and VTT instead of transcript_after", () => {
    const transcriptJob = {
      id: "run-1",
      parent_job_id: "proj-1",
      effect: "transcribe" as const,
      status: "completed" as const,
      source_filename: "clip.wav",
      source_url: "/api/jobs/run-1/source",
      source_peaks_url: "/api/jobs/run-1/source/peaks",
      source_artifact_id: null,
      duration_seconds: 10,
      sample_rate: 48000,
      fps: "25",
      pipeline_config: {
        noise_reduction: false,
        enhance: false,
        enhance_mix: 0.8,
        studio_chain: DEFAULT_STUDIO,
        separate_music: false,
        separate_speakers: false,
        transcribe: true,
        rough_cut: true,
        transcription_languages: ["en" as const],
        arabic_dialect: "auto" as const,
        audio_format: "mp3" as const,
      },
      speaker_roles: {},
      stage_states: {},
      error_code: null,
      created_at: "2026-11-20T00:00:00Z",
      started_at: null,
      completed_at: null,
      artifacts: [
        {
          id: "before-srt",
          kind: "transcript_before",
          label: "Transcript (Before Cut)",
          format: "srt",
          size_bytes: 10,
          download_url: "/api/jobs/run-1/artifacts/before-srt/download",
          content_url: "/api/jobs/run-1/artifacts/before-srt/content",
          peaks_url: "/api/jobs/run-1/artifacts/before-srt/peaks",
        },
        {
          id: "after-srt",
          kind: "transcript_after",
          label: "Transcript (After Cut)",
          format: "srt",
          size_bytes: 10,
          download_url: "/api/jobs/run-1/artifacts/after-srt/download",
          content_url: "/api/jobs/run-1/artifacts/after-srt/content",
          peaks_url: "/api/jobs/run-1/artifacts/after-srt/peaks",
        },
        {
          id: "before-vtt",
          kind: "transcript_before",
          label: "Transcript (Before Cut)",
          format: "vtt",
          size_bytes: 10,
          download_url: "/api/jobs/run-1/artifacts/before-vtt/download",
          content_url: "/api/jobs/run-1/artifacts/before-vtt/content",
          peaks_url: "/api/jobs/run-1/artifacts/before-vtt/peaks",
        },
        {
          id: "after-vtt",
          kind: "transcript_after",
          label: "Transcript (After Cut)",
          format: "vtt",
          size_bytes: 10,
          download_url: "/api/jobs/run-1/artifacts/after-vtt/download",
          content_url: "/api/jobs/run-1/artifacts/after-vtt/content",
          peaks_url: "/api/jobs/run-1/artifacts/after-vtt/peaks",
        },
      ],
    };

    render(
      <Inspector
        effects={[]}
        applying={null}
        onApply={vi.fn()}
        inputLabel="Original audio"
        error={null}
        shortfall={null}
        transcriptJob={transcriptJob}
        speakerJob={null}
        onSpeakerUpdated={() => {}}
        defaultMix={0.8}
        defaultStudio={DEFAULT_STUDIO}
        defaultLanguages={["en"]}
        defaultAudioFormat="mp3"
        defaultDialect="auto"
      />,
    );

    expect(screen.getByRole("link", { name: "SRT" })).toHaveAttribute(
      "href",
      "/api/jobs/run-1/artifacts/before-srt/download",
    );
    expect(screen.getByRole("link", { name: "VTT" })).toHaveAttribute(
      "href",
      "/api/jobs/run-1/artifacts/before-vtt/download",
    );
  });

  it("applies the Heavy Echo preset and sends dereverb setting", async () => {
    const onApply = renderInspector();
    const user = userEvent.setup();

    const heavyEcho = screen.getByRole("button", { name: "Heavy Echo" });
    await user.click(heavyEcho);
    expect(heavyEcho).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Apply enhancement" }));

    const args = onApply.mock.calls[0];
    expect(args[0]).toBe("enhance");
    expect(args[1]).toBe(0.85);
    expect(args[2]).toMatchObject({
      highpass_hz: 85,
      gate_enabled: true,
      gate_threshold_db: -35,
      gate_range_db: -18,
      gate_ratio: 3.0,
    });
    expect(args[6]).toBe(true);
  });

  it("sends dereverb=false when room echo removal is unchecked", async () => {
    const onApply = renderInspector();
    const user = userEvent.setup();

    const checkbox = screen.getByRole("checkbox", {
      name: /remove room echo/i,
    });
    expect(checkbox).toBeChecked();
    await user.click(checkbox);
    expect(checkbox).not.toBeChecked();

    await user.click(screen.getByRole("button", { name: "Apply enhancement" }));

    const args = onApply.mock.calls[0];
    expect(args[0]).toBe("enhance");
    expect(args[6]).toBe(false);
  });
});
