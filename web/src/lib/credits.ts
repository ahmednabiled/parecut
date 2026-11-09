import type { PipelineConfig } from "../api/types";

export function estimateCredits(durationSeconds: number | null): number {
  return Math.max(1, Math.ceil((durationSeconds ?? 0) / 60));
}

export function validatePipeline(config: PipelineConfig): string | null {
  if (config.rough_cut && !config.transcribe) {
    return "Rough cut needs transcription enabled.";
  }
  return null;
}
