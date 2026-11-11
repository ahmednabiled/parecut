import { useState } from "react";
import type { EffectName, Job } from "../../api/types";
import {
  EFFECTS,
  latestRun,
  RUNNING_STATUSES,
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
  onApply: (effect: EffectName, enhanceMix?: number) => void;
  error: string | null;
  shortfall: Shortfall | null;
  transcriptJob: Job | null;
  speakerJob: Job | null;
  onSpeakerUpdated: () => void;
  defaultMix: number;
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

function EffectRow({
  definition,
  run,
  busy,
  disabled,
  mix,
  onMix,
  onApply,
}: {
  definition: EffectDefinition;
  run: Job | null;
  busy: boolean;
  disabled: boolean;
  mix: number;
  onMix: (value: number) => void;
  onApply: (enhanceMix?: number) => void;
}) {
  const running = run !== null && RUNNING_STATUSES.has(run.status);
  const isEnhance = definition.name === "enhance";

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
        </div>
      ) : null}

      <button
        type="button"
        disabled={disabled}
        onClick={() => onApply(isEnhance ? mix / 100 : undefined)}
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
  error,
  shortfall,
  transcriptJob,
  speakerJob,
  onSpeakerUpdated,
  defaultMix,
}: InspectorProps) {
  const [mix, setMix] = useState(() =>
    Math.max(0, Math.min(100, Math.round(defaultMix * 100))),
  );

  const srt = transcriptJob?.artifacts.find(
    (artifact) =>
      artifact.kind === "transcript_after" && artifact.format === "srt",
  );
  const vtt = transcriptJob?.artifacts.find(
    (artifact) =>
      artifact.kind === "transcript_after" && artifact.format === "vtt",
  );
  const roughCut = transcriptJob?.artifacts.find(
    (artifact) => artifact.kind === "rough_cut_md",
  );

  return (
    <aside className="space-y-6">
      <section className="rounded-xl border border-outline-variant bg-surface-container p-5">
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
                onApply={(enhanceMix) => onApply(definition.name, enhanceMix)}
              />
            );
          })}
        </div>
      </section>

      <section className="rounded-xl border border-outline-variant bg-surface-container p-5">
        <h2 className="text-[15px] font-medium text-on-surface">
          Transcript &amp; cut
        </h2>
        <p className="mt-1 text-[12px] leading-5 text-on-surface-variant">
          {transcriptJob
            ? "Raw outputs from the transcription run. Captions in the viewer can be corrected before download."
            : "Apply Transcribe & rough cut to produce captions and the cut plan."}
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
            <SpeakerRoles job={speakerJob} onUpdated={onSpeakerUpdated} />
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
