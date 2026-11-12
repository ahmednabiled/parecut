import type { PipelineConfig } from "../api/types";
import Icon from "./Icon";

interface PipelineTogglesProps {
  config: PipelineConfig;
  onChange: (config: PipelineConfig) => void;
  disabled?: boolean;
}

type StageKey = Exclude<
  keyof PipelineConfig,
  "enhance_mix" | "studio_chain" | "transcription_languages"
>;

const STAGES: {
  key: StageKey;
  title: string;
  description: string;
}[] = [
  {
    key: "noise_reduction",
    title: "Noise reduction",
    description: "Spectral gating, de-hum, de-click, and loudness normalization.",
  },
  {
    key: "enhance",
    title: "AI voice enhancement",
    description: "Neural dereverb and bandwidth restoration for a closer, cleaner voice.",
  },
  {
    key: "separate_music",
    title: "Music separation",
    description: "Split background music from dialogue.",
  },
  {
    key: "separate_speakers",
    title: "Speaker separation",
    description: "Split overlapping voices recorded on the same microphone.",
  },
  {
    key: "transcribe",
    title: "Transcription",
    description: "Word-level timestamps and speaker labels.",
  },
  {
    key: "rough_cut",
    title: "Rough-cut plan",
    description:
      "Identify feeder lines, false starts, retakes, and dead air. Requires transcription.",
  },
];

export default function PipelineToggles({
  config,
  onChange,
  disabled = false,
}: PipelineTogglesProps) {
  function toggle(key: StageKey, value: boolean) {
    const next = { ...config, [key]: value };
    if (key === "transcribe" && !value) {
      next.rough_cut = false;
    }
    onChange(next);
  }

  const mix = Math.round(config.enhance_mix * 100);

  return (
    <div>
      <div className="divide-y divide-outline-variant">
        {STAGES.map(({ key, title, description }) => {
          const unavailable = disabled || (key === "rough_cut" && !config.transcribe);
          return (
            <label
              key={key}
              className={`flex cursor-pointer items-start gap-3 py-4 ${
                unavailable ? "cursor-not-allowed opacity-50" : ""
              }`}
            >
              <input
                type="checkbox"
                checked={config[key]}
                disabled={unavailable}
                onChange={(event) => toggle(key, event.target.checked)}
                className="mt-0.5 size-4 shrink-0 accent-primary"
              />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-on-surface">
                  {title}
                </span>
                <span className="mt-1 block text-[13px] leading-5 text-on-surface-variant">
                  {description}
                </span>
              </span>
            </label>
          );
        })}
      </div>

      <div className={`border-t border-outline-variant pt-5 ${disabled ? "opacity-50" : ""}`}>
        <div className="flex items-center justify-between gap-4">
          <label
            htmlFor="enhance-mix"
            className="text-sm font-medium text-on-surface"
          >
            Enhancement mix
          </label>
          <span className="font-mono text-[13px] text-on-surface">{mix}%</span>
        </div>
        <input
          id="enhance-mix"
          type="range"
          min={0}
          max={100}
          step={1}
          value={mix}
          disabled={disabled || !config.enhance}
          onChange={(event) =>
            onChange({ ...config, enhance_mix: Number(event.target.value) / 100 })
          }
          className="mt-3 w-full accent-primary disabled:cursor-not-allowed disabled:opacity-50"
        />
        <p className="mt-2 flex items-start gap-2 text-[13px] leading-5 text-on-surface-variant">
          <Icon name="graphic_eq" size={16} className="mt-0.5" />
          0% keeps the DSP-cleaned signal. 100% is fully enhanced.
        </p>
      </div>
    </div>
  );
}
