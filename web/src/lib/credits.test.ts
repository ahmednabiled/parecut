import { describe, expect, it } from "vitest";
import type { PipelineConfig } from "../api/types";
import { estimateCredits, validatePipeline } from "./credits";

const complete: PipelineConfig = {
  noise_reduction: true,
  enhance: true,
  enhance_mix: 0.8,
  separate_music: true,
  separate_speakers: true,
  transcribe: true,
  rough_cut: true,
};

describe("estimateCredits", () => {
  it("rounds up to whole minutes with a one-minute floor", () => {
    expect(estimateCredits(null)).toBe(1);
    expect(estimateCredits(2)).toBe(1);
    expect(estimateCredits(61)).toBe(2);
  });
});

describe("validatePipeline", () => {
  it("rejects rough cut without transcription", () => {
    expect(validatePipeline({ ...complete, transcribe: false, rough_cut: true })).toBe(
      "Rough cut needs transcription enabled.",
    );
    expect(validatePipeline(complete)).toBeNull();
  });
});
