import type { StageStatus } from "../api/types";

export const STAGES = [
  { key: "noise_reduction", label: "Noise reduction" },
  { key: "enhance", label: "Voice enhancement" },
  { key: "separate_music", label: "Music separation" },
  { key: "separate_speakers", label: "Speaker separation" },
  { key: "transcribe", label: "Transcription" },
  { key: "rough_cut", label: "Rough-cut plan" },
] as const;

export type StageKey = (typeof STAGES)[number]["key"];

export const STAGE_STATUS_LABELS: Record<StageStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Done",
  skipped: "Skipped",
  failed: "Failed",
};
