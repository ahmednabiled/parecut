import type {
  EffectName,
  Job,
  StudioChain,
  TranscriptionLanguage,
} from "../api/types";

export const DEFAULT_LANGUAGES: TranscriptionLanguage[] = ["en"];

export const TRANSCRIPTION_LANGUAGES: {
  code: TranscriptionLanguage;
  label: string;
}[] = [
  { code: "en", label: "English" },
  { code: "ar", label: "Arabic" },
];

export const DEFAULT_STUDIO: StudioChain = {
  enabled: true,
  highpass_hz: 75,
  body_db: 2,
  mud_db: -2,
  presence_db: 1.5,
  deesser: 0.35,
  compressor_threshold_db: -18,
  compressor_ratio: 2.5,
  compressor_attack_ms: 15,
  compressor_release_ms: 150,
  limiter_db: -1,
  loudness_lufs: -16,
};

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
      "Resemble Enhance restores bandwidth and body at 44.1 kHz. The mix blends it over the denoised track; CPU runs can take a few minutes.",
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
