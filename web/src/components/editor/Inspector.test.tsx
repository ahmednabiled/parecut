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
      error={null}
      shortfall={null}
      transcriptJob={null}
      speakerJob={null}
      onSpeakerUpdated={() => {}}
      defaultMix={0.8}
      defaultStudio={DEFAULT_STUDIO}
      defaultLanguages={["en"]}
      defaultAudioFormat="mp3"
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
});
