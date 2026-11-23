import { useId, useState } from "react";
import type {
  ArabicDialect,
  AudioFormat,
  EffectName,
  Job,
  StudioChain,
  TranscriptionLanguage,
} from "../../api/types";
import {
  ARABIC_DIALECTS,
  AUDIO_FORMATS,
  DEFAULT_ARABIC_DIALECT,
  DEFAULT_AUDIO_FORMAT,
  DEFAULT_LANGUAGES,
  DEFAULT_STUDIO,
  EFFECTS,
  latestRun,
  RUNNING_STATUSES,
  TRANSCRIPTION_LANGUAGES,
  type EffectDefinition,
} from "../../lib/effects";
import Icon from "../Icon";
import SpeakerRoles from "../SpeakerRoles";

interface Shortfall {
  required: number;
  available: number;
}

interface InspectorProps {
  effects: Job[];
  applying: EffectName | null;
  onApply: (
    effect: EffectName,
    enhanceMix?: number,
    studio?: StudioChain,
    languages?: TranscriptionLanguage[],
    audioFormat?: AudioFormat,
    arabicDialect?: ArabicDialect,
  ) => void;
  inputLabel: string;
  error: string | null;
  shortfall: Shortfall | null;
  transcriptJob: Job | null;
  speakerJob: Job | null;
  onSpeakerUpdated: () => void;
  defaultMix: number;
  defaultStudio: StudioChain;
  defaultLanguages: TranscriptionLanguage[];
  defaultAudioFormat: AudioFormat;
  defaultDialect: ArabicDialect;
}

const STATUS_STYLES: Record<string, string> = {
  queued: "border border-outline-variant text-on-surface-variant",
  running: "bg-surface-container-high text-on-surface",
  completed: "bg-primary text-on-primary",
  failed: "bg-error-container text-on-error-container",
};

const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Processing",
  completed: "Applied",
  failed: "Failed",
};

function RunState({ run }: { run: Job | null }) {
  if (!run) return null;
  return (
    <span
      className={`inline-flex h-6 shrink-0 items-center gap-2 rounded-lg px-2 text-[11px] font-medium ${STATUS_STYLES[run.status] ?? STATUS_STYLES.queued}`}
    >
      {RUNNING_STATUSES.has(run.status) ? (
        <span className="spinner" aria-hidden="true" />
      ) : null}
      {STATUS_LABELS[run.status] ?? run.status}
    </span>
  );
}

function formatDb(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)} dB`;
}

function StudioSlider({
  label,
  value,
  min,
  max,
  step,
  display,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  display: string;
  onChange: (value: number) => void;
}) {
  const id = useId();
  return (
    <div>
      <div className="flex items-center justify-between gap-3 text-[11px] text-on-surface-variant">
        <label htmlFor={id}>{label}</label>
        <span className="font-mono text-on-surface">{display}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-1.5 h-1 w-full cursor-pointer accent-[#ededed]"
      />
    </div>
  );
}

function StudioGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-on-surface-variant">
        {title}
      </p>
      <div className="mt-2.5 space-y-3">{children}</div>
    </div>
  );
}

function StudioPanel({
  studio,
  onChange,
  open,
  onToggle,
}: {
  studio: StudioChain;
  onChange: (studio: StudioChain) => void;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="mt-4 rounded-lg border border-outline-variant bg-surface-container-low">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
      >
        <span className="flex items-center gap-2 text-[12px] font-medium text-on-surface">
          <Icon name="tune" size={14} />
          Studio polish
        </span>
        <span className="flex items-center gap-2 text-[11px] text-on-surface-variant">
          {studio.enabled ? "On" : "Off"}
          <Icon
            name={open ? "keyboard_arrow_up" : "keyboard_arrow_down"}
            size={16}
          />
        </span>
      </button>

      {open ? (
        <div className="border-t border-outline-variant px-3 py-3">
          <label className="flex items-center justify-between gap-3 text-[12px] text-on-surface">
            Apply studio chain
            <input
              type="checkbox"
              checked={studio.enabled}
              onChange={(event) =>
                onChange({ ...studio, enabled: event.target.checked })
              }
              className="size-4 accent-[#ededed]"
            />
          </label>
          <p className="mt-1 text-[11px] leading-4 text-on-surface-variant">
            Tone, de-essing, compression, limiting, then loudness
            normalization after Resemble.
          </p>

          <div className="mt-4 space-y-4">
            <StudioGroup title="Tone">
              <StudioSlider
                label="High-pass"
                value={studio.highpass_hz}
                min={20}
                max={200}
                step={5}
                display={`${Math.round(studio.highpass_hz)} Hz`}
                onChange={(value) =>
                  onChange({ ...studio, highpass_hz: value })
                }
              />
              <StudioSlider
                label="Body"
                value={studio.body_db}
                min={-12}
                max={12}
                step={0.5}
                display={formatDb(studio.body_db)}
                onChange={(value) => onChange({ ...studio, body_db: value })}
              />
              <StudioSlider
                label="Mud cut"
                value={studio.mud_db}
                min={-12}
                max={6}
                step={0.5}
                display={formatDb(studio.mud_db)}
                onChange={(value) => onChange({ ...studio, mud_db: value })}
              />
              <StudioSlider
                label="Presence"
                value={studio.presence_db}
                min={-12}
                max={12}
                step={0.5}
                display={formatDb(studio.presence_db)}
                onChange={(value) =>
                  onChange({ ...studio, presence_db: value })
                }
              />
            </StudioGroup>

            <StudioGroup title="Dynamics">
              <StudioSlider
                label="De-ess"
                value={studio.deesser}
                min={0}
                max={1}
                step={0.05}
                display={`${Math.round(studio.deesser * 100)}%`}
                onChange={(value) => onChange({ ...studio, deesser: value })}
              />
              <StudioSlider
                label="Threshold"
                value={studio.compressor_threshold_db}
                min={-60}
                max={0}
                step={1}
                display={formatDb(studio.compressor_threshold_db)}
                onChange={(value) =>
                  onChange({ ...studio, compressor_threshold_db: value })
                }
              />
              <StudioSlider
                label="Ratio"
                value={studio.compressor_ratio}
                min={1}
                max={8}
                step={0.1}
                display={`${studio.compressor_ratio.toFixed(1)}:1`}
                onChange={(value) =>
                  onChange({ ...studio, compressor_ratio: value })
                }
              />
              <StudioSlider
                label="Attack"
                value={studio.compressor_attack_ms}
                min={1}
                max={100}
                step={1}
                display={`${Math.round(studio.compressor_attack_ms)} ms`}
                onChange={(value) =>
                  onChange({ ...studio, compressor_attack_ms: value })
                }
              />
              <StudioSlider
                label="Release"
                value={studio.compressor_release_ms}
                min={20}
                max={500}
                step={10}
                display={`${Math.round(studio.compressor_release_ms)} ms`}
                onChange={(value) =>
                  onChange({ ...studio, compressor_release_ms: value })
                }
              />
            </StudioGroup>

            <StudioGroup title="Output">
              <StudioSlider
                label="Limiter"
                value={studio.limiter_db}
                min={-12}
                max={0}
                step={0.5}
                display={formatDb(studio.limiter_db)}
                onChange={(value) => onChange({ ...studio, limiter_db: value })}
              />
              <StudioSlider
                label="Loudness"
                value={studio.loudness_lufs}
                min={-30}
                max={-8}
                step={0.5}
                display={`${studio.loudness_lufs.toFixed(1)} LUFS`}
                onChange={(value) =>
                  onChange({ ...studio, loudness_lufs: value })
                }
              />
            </StudioGroup>
          </div>

          <button
            type="button"
            onClick={() => onChange(DEFAULT_STUDIO)}
            className="mt-4 inline-flex h-7 items-center gap-1.5 rounded-[14px] border border-outline px-2.5 text-[11px] font-medium text-on-surface-variant transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface"
          >
            <Icon name="restart_alt" size={13} />
            Reset
          </button>
        </div>
      ) : null}
    </div>
  );
}

function LanguagePicker({
  languages,
  onToggle,
  dialect,
  onDialect,
}: {
  languages: TranscriptionLanguage[];
  onToggle: (language: TranscriptionLanguage) => void;
  dialect: ArabicDialect;
  onDialect: (dialect: ArabicDialect) => void;
}) {
  const arabic = languages.includes("ar");
  return (
    <div className="mt-4">
      <p className="text-[12px] font-medium text-on-surface">
        Languages in the soundtrack
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {TRANSCRIPTION_LANGUAGES.map(({ code, label }) => {
          const active = languages.includes(code);
          return (
            <button
              key={code}
              type="button"
              aria-pressed={active}
              onClick={() => onToggle(code)}
              className={`inline-flex h-7 items-center rounded-full border px-3 text-[11px] font-medium transition-colors duration-150 ease-standard focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-on-surface ${
                active
                  ? "border-primary bg-primary text-on-primary"
                  : "border-outline text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>

      {arabic ? (
        <div className="mt-3">
          <p className="text-[12px] font-medium text-on-surface">
            Arabic dialect
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {ARABIC_DIALECTS.map(({ code, label }) => {
              const active = dialect === code;
              return (
                <button
                  key={code}
                  type="button"
                  aria-pressed={active}
                  onClick={() => onDialect(code)}
                  className={`inline-flex h-6 items-center rounded-full border px-2.5 text-[10px] font-medium transition-colors duration-150 ease-standard focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-on-surface ${
                    active
                      ? "border-primary bg-primary text-on-primary"
                      : "border-outline-variant text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-[11px] leading-4 text-on-surface-variant">
            Arabic uses a dialect-tuned Whisper model. Pick the closest dialect
            so the vocabulary and spelling match the speaker.
          </p>
        </div>
      ) : null}

      <p className="mt-2 text-[11px] leading-4 text-on-surface-variant">
        Select every language present. Multiple languages run the model once per
        language and merge the results, so processing takes longer.
      </p>
    </div>
  );
}

function EffectRow({
  definition,
  run,
  busy,
  disabled,
  mix,
  onMix,
  studio,
  onStudio,
  studioOpen,
  onStudioOpen,
  languages,
  onLanguages,
  dialect,
  onDialect,
  onApply,
}: {
  definition: EffectDefinition;
  run: Job | null;
  busy: boolean;
  disabled: boolean;
  mix: number;
  onMix: (value: number) => void;
  studio: StudioChain;
  onStudio: (studio: StudioChain) => void;
  studioOpen: boolean;
  onStudioOpen: () => void;
  languages: TranscriptionLanguage[];
  onLanguages: (language: TranscriptionLanguage) => void;
  dialect: ArabicDialect;
  onDialect: (dialect: ArabicDialect) => void;
  onApply: (
    enhanceMix?: number,
    studio?: StudioChain,
    languages?: TranscriptionLanguage[],
    arabicDialect?: ArabicDialect,
  ) => void;
}) {
  const running = run !== null && RUNNING_STATUSES.has(run.status);
  const isEnhance = definition.name === "enhance";
  const isTranscribe = definition.name === "transcribe";

  return (
    <article className="border-t border-outline-variant py-5 first:border-t-0 first:pt-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[14px] font-medium text-on-surface">
            {definition.label}
          </h3>
          <p className="mt-1 text-[12px] leading-5 text-on-surface-variant">
            {definition.description}
          </p>
        </div>
        <RunState run={run} />
      </div>

      {isEnhance ? (
        <div className="mt-4">
          <div className="flex items-center justify-between text-[12px] text-on-surface-variant">
            <label htmlFor="enhance-mix">Mix</label>
            <span className="font-mono text-on-surface">{mix}%</span>
          </div>
          <input
            id="enhance-mix"
            type="range"
            min={0}
            max={100}
            step={5}
            value={mix}
            disabled={busy || running}
            onChange={(event) => onMix(Number(event.target.value))}
            className="mt-2 h-1.5 w-full cursor-pointer accent-[#ededed] disabled:cursor-not-allowed disabled:opacity-50"
          />
          <StudioPanel
            studio={studio}
            onChange={onStudio}
            open={studioOpen}
            onToggle={onStudioOpen}
          />
        </div>
      ) : null}

      {isTranscribe ? (
        <LanguagePicker
          languages={languages}
          onToggle={onLanguages}
          dialect={dialect}
          onDialect={onDialect}
        />
      ) : null}

      <button
        type="button"
        disabled={disabled}
        onClick={() =>
          onApply(
            isEnhance ? mix / 100 : undefined,
            isEnhance ? studio : undefined,
            isTranscribe ? languages : undefined,
            isTranscribe && languages.includes("ar") ? dialect : undefined,
          )
        }
        className="mt-4 inline-flex h-8 items-center gap-2 rounded-[16px] border border-outline px-3 text-[12px] font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? <span className="spinner" aria-hidden="true" /> : null}
        {busy
          ? "Applying…"
          : run?.status === "completed"
            ? "Apply again"
            : definition.action}
      </button>
    </article>
  );
}

function DownloadLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      download
      className="inline-flex h-8 items-center gap-1.5 rounded-[16px] border border-outline px-3 text-[12px] font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high"
    >
      <Icon name="download" size={14} />
      {children}
    </a>
  );
}

export default function Inspector({
  effects,
  applying,
  onApply,
  inputLabel,
  error,
  shortfall,
  transcriptJob,
  speakerJob,
  onSpeakerUpdated,
  defaultMix,
  defaultStudio,
  defaultLanguages,
  defaultAudioFormat,
  defaultDialect,
}: InspectorProps) {
  const [mix, setMix] = useState(() =>
    Math.max(0, Math.min(100, Math.round(defaultMix * 100))),
  );
  const [studio, setStudio] = useState<StudioChain>(() => ({
    ...DEFAULT_STUDIO,
    ...defaultStudio,
  }));
  const [studioOpen, setStudioOpen] = useState(false);
  const lastTranscribe = latestRun(effects, "transcribe");
  const lastAudioRun = [...effects].reverse().find((run) => {
    const definition = EFFECTS.find((item) => item.name === run.effect);
    return definition?.producesAudio;
  });

  const [languageOverride, setLanguageOverride] = useState<{
    runId: string | undefined;
    value: TranscriptionLanguage[];
  } | null>(null);
  const [dialectOverride, setDialectOverride] = useState<{
    runId: string | undefined;
    value: ArabicDialect;
  } | null>(null);
  const [audioFormatOverride, setAudioFormatOverride] = useState<{
    runId: string | undefined;
    value: AudioFormat;
  } | null>(null);

  const baseLanguages = (() => {
    const fromRun = lastTranscribe?.pipeline_config.transcription_languages;
    if (fromRun && fromRun.length > 0) return fromRun;
    const initial = (defaultLanguages ?? DEFAULT_LANGUAGES).filter(
      (language) => language === "en" || language === "ar",
    );
    return initial.length > 0 ? initial : DEFAULT_LANGUAGES;
  })();
  const languages =
    languageOverride !== null && languageOverride.runId === lastTranscribe?.id
      ? languageOverride.value
      : baseLanguages;

  const dialect =
    dialectOverride !== null && dialectOverride.runId === lastTranscribe?.id
      ? dialectOverride.value
      : (lastTranscribe?.pipeline_config.arabic_dialect ??
        defaultDialect ??
        DEFAULT_ARABIC_DIALECT);

  const runAudioFormat = lastAudioRun?.pipeline_config.audio_format;
  const audioFormat =
    audioFormatOverride !== null && audioFormatOverride.runId === lastAudioRun?.id
      ? audioFormatOverride.value
      : runAudioFormat === "mp3" || runAudioFormat === "wav"
        ? runAudioFormat
        : (defaultAudioFormat ?? DEFAULT_AUDIO_FORMAT);

  function toggleLanguage(language: TranscriptionLanguage) {
    const next = languages.includes(language)
      ? languages.length === 1
        ? languages
        : languages.filter((item) => item !== language)
      : [...languages, language];
    setLanguageOverride({ runId: lastTranscribe?.id, value: next });
  }

  function setDialect(value: ArabicDialect) {
    setDialectOverride({ runId: lastTranscribe?.id, value });
  }

  function setAudioFormat(value: AudioFormat) {
    setAudioFormatOverride({ runId: lastAudioRun?.id, value });
  }

  const srt = transcriptJob?.artifacts.find(
    (artifact) =>
      artifact.kind === "transcript_before" && artifact.format === "srt",
  );
  const vtt = transcriptJob?.artifacts.find(
    (artifact) =>
      artifact.kind === "transcript_before" && artifact.format === "vtt",
  );
  const roughCut = transcriptJob?.artifacts.find(
    (artifact) => artifact.kind === "rough_cut_md",
  );

  return (
    <aside className="min-w-0 space-y-6 xl:h-full xl:min-h-0 xl:overflow-y-auto xl:overflow-x-hidden xl:overscroll-contain xl:pr-1">
      <section className="min-w-0 rounded-xl border border-outline-variant bg-surface-container p-5">
        <h2 className="text-[15px] font-medium text-on-surface">Inspector</h2>
        <p className="mt-1 text-[12px] leading-5 text-on-surface-variant">
          Effects are non-destructive. Each run reserves credits when it starts
          and adds its output as a muted track.
        </p>

        {shortfall ? (
          <div className="mt-4 rounded-lg border border-error/25 bg-error-container p-3">
            <p className="text-[13px] text-on-error-container">
              Insufficient credits: need {shortfall.required}, have{" "}
              {shortfall.available}.
            </p>
            <p className="mt-1 text-[12px] leading-5 text-on-error-container/80">
              The original project is untouched. Top up, then apply the effect
              again.
            </p>
          </div>
        ) : null}

        {error ? (
          <p
            role="alert"
            className="mt-4 rounded-lg border border-error/25 bg-error-container px-3 py-2 text-[13px] text-on-error-container"
          >
            {error}
          </p>
        ) : null}

        <div className="mt-5 rounded-lg border border-outline-variant bg-surface-container-low px-3 py-2.5">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-[12px] text-on-surface-variant">
              Effects apply to
            </p>
            <p className="min-w-0 truncate text-[12px] font-medium text-on-surface">
              {inputLabel}
            </p>
          </div>
          <p className="mt-1 text-[11px] leading-4 text-on-surface-variant">
            Click a track name in the timeline to change the input.
          </p>
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-outline-variant bg-surface-container-low px-3 py-2.5">
          <div className="min-w-0">
            <p className="text-[12px] font-medium text-on-surface">
              Generated audio
            </p>
            <p className="mt-0.5 text-[11px] leading-4 text-on-surface-variant">
              MP3 is small and streams fast. WAV is lossless and larger.
            </p>
          </div>
          <div
            role="group"
            aria-label="Generated audio format"
            className="inline-flex h-8 shrink-0 items-center rounded-full border border-outline-variant p-0.5"
          >
            {AUDIO_FORMATS.map(({ code, label }) => (
              <button
                key={code}
                type="button"
                aria-pressed={audioFormat === code}
                onClick={() => setAudioFormat(code)}
                className={`h-6 rounded-full px-2.5 text-[11px] font-medium transition-colors duration-150 ease-standard ${
                  audioFormat === code
                    ? "bg-primary text-on-primary"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5">
          {EFFECTS.map((definition) => {
            const run = latestRun(effects, definition.name);
            const busy = applying === definition.name;
            const locked = busy || applying !== null || running(run);
            return (
              <EffectRow
                key={definition.name}
                definition={definition}
                run={run}
                busy={busy}
                disabled={locked}
                mix={mix}
                onMix={setMix}
                studio={studio}
                onStudio={setStudio}
                studioOpen={studioOpen}
                onStudioOpen={() => setStudioOpen((open) => !open)}
                languages={languages}
                onLanguages={toggleLanguage}
                dialect={dialect}
                onDialect={setDialect}
                onApply={(
                  enhanceMix,
                  studioSettings,
                  languageSettings,
                  arabicDialect,
                ) =>
                  onApply(
                    definition.name,
                    enhanceMix,
                    studioSettings,
                    languageSettings,
                    definition.producesAudio ? audioFormat : undefined,
                    arabicDialect,
                  )
                }
              />
            );
          })}
        </div>
      </section>

      <section className="min-w-0 rounded-xl border border-outline-variant bg-surface-container p-5">
        <h2 className="text-[15px] font-medium text-on-surface">
          Transcript &amp; cut
        </h2>
        <p className="mt-1 text-[12px] leading-5 text-on-surface-variant">
          {transcriptJob
            ? "Raw outputs for the original source file (all speakers). The viewer SRT downloads captions for the selected track."
            : "Apply Transcribe & rough cut to produce captions and the detailed transcription."}
        </p>

        {srt || vtt || roughCut ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {srt ? <DownloadLink href={srt.download_url}>SRT</DownloadLink> : null}
            {vtt ? <DownloadLink href={vtt.download_url}>VTT</DownloadLink> : null}
            {roughCut ? (
              <DownloadLink href={roughCut.download_url}>
                ROUGH-CUT.md
              </DownloadLink>
            ) : null}
          </div>
        ) : null}

        <div className="mt-5 border-t border-outline-variant pt-5">
          <h3 className="text-[13px] font-medium text-on-surface">
            Speaker roles
          </h3>
          <p className="mb-4 mt-1 text-[12px] leading-5 text-on-surface-variant">
            Feeder lines are removed from the cut. Saving regenerates the cut
            outputs.
          </p>
          {speakerJob ? (
            <SpeakerRoles
              key={speakerJob.id}
              job={speakerJob}
              onUpdated={onSpeakerUpdated}
            />
          ) : (
            <p className="text-[13px] leading-5 text-on-surface-variant">
              Speaker roles appear after transcription finishes.
            </p>
          )}
        </div>
      </section>
    </aside>
  );
}

function running(run: Job | null): boolean {
  return run !== null && RUNNING_STATUSES.has(run.status);
}
