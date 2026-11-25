import type {
  ArabicDialect,
  AudioFormat,
  EffectName,
  Job,
  StudioChain,
  TranscriptionLanguage,
} from "../api/types";

export const DEFAULT_LANGUAGES: TranscriptionLanguage[] = ["en"];
export const DEFAULT_AUDIO_FORMAT: AudioFormat = "mp3";
export const DEFAULT_ARABIC_DIALECT: ArabicDialect = "auto";

export const AUDIO_FORMATS: { code: AudioFormat; label: string }[] = [
  { code: "mp3", label: "Standard (MP3)" },
  { code: "wav", label: "Lossless (WAV)" },
];

export const TRANSCRIPTION_LANGUAGES: {
  code: TranscriptionLanguage;
  label: string;
}[] = [
  { code: "en", label: "English" },
  { code: "ar", label: "Arabic" },
];

export const ARABIC_DIALECTS: {
  code: ArabicDialect;
  label: string;
}[] = [
  { code: "auto", label: "Auto" },
  { code: "msa", label: "Standard (MSA)" },
  { code: "egyptian", label: "Egyptian" },
  { code: "gulf", label: "Gulf" },
  { code: "levantine", label: "Levantine" },
  { code: "maghrebi", label: "Maghrebi" },
  { code: "iraqi", label: "Iraqi" },
];

export const DEFAULT_STUDIO: StudioChain = {
  enabled: true,
  highpass_hz: 75,
  gate_enabled: true,
  gate_threshold_db: -40,
  gate_range_db: -12,
  gate_ratio: 2,
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

export interface EnhancePreset {
  id: "natural" | "broadcast" | "heavy_echo";
  label: string;
  mix: number;
  dereverb: boolean;
  studio: StudioChain;
}

export const ENHANCE_PRESETS: EnhancePreset[] = [
  {
    id: "natural",
    label: "Natural",
    mix: 65,
    dereverb: true,
    studio: {
      ...DEFAULT_STUDIO,
      body_db: 1.5,
      mud_db: -1.5,
      presence_db: 1.0,
      gate_threshold_db: -42,
      gate_range_db: -10,
      gate_ratio: 1.8,
      compressor_ratio: 2.0,
    },
  },
  {
    id: "broadcast",
    label: "Broadcast",
    mix: 75,
    dereverb: true,
    studio: { ...DEFAULT_STUDIO },
  },
  {
    id: "heavy_echo",
    label: "Heavy Echo",
    mix: 85,
    dereverb: true,
    studio: {
      ...DEFAULT_STUDIO,
      highpass_hz: 85,
      body_db: 1.5,
      mud_db: -3.0,
      presence_db: 2.0,
      gate_threshold_db: -35,
      gate_range_db: -18,
      gate_ratio: 3.0,
      compressor_threshold_db: -20,
      compressor_ratio: 3.0,
    },
  },
];

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
      "De-Reverb strips room echo, Resemble Enhance restores bandwidth at 44.1 kHz, and Studio polish tightens tone and dynamics.",
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
