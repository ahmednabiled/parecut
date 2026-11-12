import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PipelineConfig } from "../api/types";
import { DEFAULT_STUDIO } from "../lib/effects";
import PipelineToggles from "./PipelineToggles";

const complete: PipelineConfig = {
  noise_reduction: true,
  enhance: true,
  enhance_mix: 0.8,
  studio_chain: DEFAULT_STUDIO,
  separate_music: true,
  separate_speakers: true,
  transcribe: true,
  rough_cut: true,
};

describe("PipelineToggles", () => {
  it("clears rough cut when transcription is disabled", async () => {
    const onChange = vi.fn();
    render(<PipelineToggles config={complete} onChange={onChange} />);

    await userEvent.click(
      screen.getByRole("checkbox", { name: /^transcription/i }),
    );

    expect(onChange).toHaveBeenCalledWith({
      ...complete,
      transcribe: false,
      rough_cut: false,
    });
  });

  it("disables rough cut while transcription is off", () => {
    render(
      <PipelineToggles
        config={{ ...complete, transcribe: false, rough_cut: false }}
        onChange={() => {}}
      />,
    );

    expect(
      screen.getByRole("checkbox", { name: /^rough-cut plan/i }),
    ).toBeDisabled();
  });
});
