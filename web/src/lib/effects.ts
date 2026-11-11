import type { EffectName, Job } from "../api/types";

export interface EffectDefinition {
  name: EffectName;
  label: string;
  action: string;
  description: string;
  producesAudio: boolean;
}

export const EFFECTS: EffectDefinition[] = [
  {
    name: "noise_reduction",
    label: "Noise reduction",
    action: "Apply denoise",
    description:
      "DeepFilterNet3 removes steady hiss, hum, and room tone and adds a cleaned track.",
    producesAudio: true,
  },
  {
    name: "enhance",
    label: "Enhance",
    action: "Apply enhancement",
    description:
      "Neural dereverb and bandwidth restoration. The mix leans the result back toward the original.",
    producesAudio: true,
  },
  {
    name: "separate_music",
    label: "Music separation",
    action: "Split music",
    description:
      "Demucs separates the music bed from dialogue so you can keep or drop it.",
    producesAudio: true,
  },
  {
    name: "separate_speakers",
    label: "Speaker separation",
    action: "Split speakers",
    description:
      "Gates each detected voice into its own synchronized stem.",
    producesAudio: true,
  },
  {
    name: "transcribe",
    label: "Transcribe & rough cut",
    action: "Transcribe",
    description:
      "Speaker-attributed captions plus a cut plan for feeder lines, false starts, retakes, and dead air.",
    producesAudio: false,
  },
];

export const AUDIO_KINDS = new Set([
  "cleaned_audio",
  "enhanced_audio",
  "stem_music",
  "stem_dialogue",
  "stem_speaker",
]);

export const RUNNING_STATUSES = new Set(["queued", "running"]);

export function effectLabel(effect: EffectName | null | undefined): string {
  return EFFECTS.find((item) => item.name === effect)?.label ?? "Effect";
}

export function latestRun(effects: Job[], effect: EffectName): Job | null {
  for (let index = effects.length - 1; index >= 0; index -= 1) {
    if (effects[index].effect === effect) {
      return effects[index];
    }
  }
  return null;
}
