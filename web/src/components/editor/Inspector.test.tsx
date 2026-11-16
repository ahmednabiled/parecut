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
});
