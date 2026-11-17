import { useState } from "react";
import {
  captionCueKey,
  type CaptionCue,
} from "../../lib/captions";
import { formatMediaTime } from "../../lib/format";
import Icon from "../Icon";

interface ViewerProps {
  cues: CaptionCue[];
  currentTime: number;
  chunkWords: number;
  onChunkWords: (value: number) => void;
  onSeek: (time: number) => void;
  onEditCue: (cue: CaptionCue, text: string) => void;
  onDownload: () => void;
  loading: boolean;
  error: boolean;
  hasTranscript: boolean;
  variant: "before" | "after";
  onVariant: (variant: "before" | "after") => void;
}

function cueForTime(cues: CaptionCue[], time: number): CaptionCue | null {
  let current: CaptionCue | null = null;
  for (const cue of cues) {
    if (cue.start > time) break;
    current = cue;
    if (time < cue.end) return cue;
  }
  return current ?? cues[0] ?? null;
}

export default function Viewer({
  cues,
  currentTime,
  chunkWords,
  onChunkWords,
  onSeek,
  onEditCue,
  onDownload,
  loading,
  error,
  hasTranscript,
  variant,
  onVariant,
}: ViewerProps) {
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const current =
    cueForTime(cues, currentTime) ?? null;

  function startEditing(cue: CaptionCue) {
    setEditingKey(captionCueKey(cue));
    setDraft(cue.text);
  }

  function commit(cue: CaptionCue) {
    const text = draft.trim();
    if (text) onEditCue(cue, text);
    setEditingKey(null);
  }

  return (
    <section className="rounded-xl border border-outline-variant bg-surface-container p-5 xl:flex xl:h-full xl:min-h-0 xl:flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-medium text-on-surface">Captions</h2>
          <p className="mt-1 text-[12px] text-on-surface-variant">
            Follows the playhead. Full is the raw transcript; After cut applies
            the cut plan.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div
            role="group"
            aria-label="Transcript version"
            className="inline-flex h-8 items-center rounded-full border border-outline-variant bg-surface-container-low p-0.5"
          >
            {(
              [
                ["before", "Full"],
                ["after", "After cut"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={variant === value}
                onClick={() => onVariant(value)}
                className={`h-7 rounded-full px-2.5 text-[11px] font-medium transition-colors duration-150 ease-standard ${
                  variant === value
                    ? "bg-primary text-on-primary"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <span className="text-[12px] text-on-surface-variant">Words</span>
          <div
            role="group"
            aria-label="Words per caption"
            className="inline-flex h-8 items-center rounded-full border border-outline-variant bg-surface-container-low p-0.5"
          >
            {[3, 5, 8].map((count) => (
              <button
                key={count}
                type="button"
                aria-pressed={chunkWords === count}
                onClick={() => onChunkWords(count)}
                className={`h-6 rounded-full px-2.5 font-mono text-[12px] font-medium transition-colors duration-150 ease-standard ${
                  chunkWords === count
                    ? "bg-primary text-on-primary"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {count}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onDownload}
            disabled={cues.length === 0}
            className="inline-flex h-8 items-center gap-1.5 rounded-[16px] border border-outline px-3 text-[12px] font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Icon name="download" size={14} />
            SRT
          </button>
        </div>
      </div>

      <div className="mt-5 flex min-h-[210px] shrink-0 items-center justify-center rounded-lg border border-outline-variant bg-surface-container-lowest px-6 py-8 text-center xl:min-h-[110px] xl:py-4">
        {loading ? (
          <p className="flex items-center gap-2 text-[13px] text-on-surface-variant">
            <span className="spinner" aria-hidden="true" />
            Loading captions
          </p>
        ) : error ? (
          <p className="text-[13px] text-on-surface-variant">
            Could not load the transcript.
          </p>
        ) : !hasTranscript ? (
          <div className="max-w-[42ch]">
            <p className="text-[15px] font-medium text-on-surface">
              No captions yet
            </p>
            <p className="mt-2 text-[13px] leading-5 text-on-surface-variant">
              Apply Transcribe &amp; rough cut in the inspector. The captions
              and the cut specification will appear here.
            </p>
          </div>
        ) : current ? (
          <div>
            <p className="text-[24px] font-medium leading-8 tracking-[-0.01em] text-on-surface">
              {current.text}
            </p>
            <p className="mt-3 font-mono text-[12px] text-on-surface-variant">
              {current.speaker} · {formatMediaTime(current.start)}
            </p>
          </div>
        ) : (
          <p className="text-[13px] text-on-surface-variant">
            Press play to follow the captions.
          </p>
        )}
      </div>

      {cues.length > 0 ? (
        <div className="mt-4 min-h-0 max-h-56 space-y-1 overflow-y-auto overscroll-contain pr-1 xl:max-h-none xl:flex-1">
          {cues.map((cue, index) => {
            const key = captionCueKey(cue);
            const active = cue === current;
            const editing = editingKey === key;
            return (
              <div
                key={`${key}-${index}`}
                className={`grid grid-cols-[4.5rem_minmax(0,1fr)_1.75rem] items-start gap-2 rounded-lg px-3 py-2 transition-colors duration-150 ease-standard ${
                  active
                    ? "bg-surface-container-high text-on-surface"
                    : "text-on-surface-variant hover:bg-surface-container-low"
                }`}
              >
                <span className="pt-0.5 font-mono text-[11px]">
                  {formatMediaTime(cue.start)}
                </span>
                {editing ? (
                  <input
                    autoFocus
                    aria-label={`Edit caption ${index + 1} at ${formatMediaTime(cue.start)}`}
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onBlur={() => commit(cue)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        commit(cue);
                      }
                      if (event.key === "Escape") {
                        event.preventDefault();
                        setEditingKey(null);
                      }
                    }}
                    className="h-7 w-full rounded border border-on-surface bg-surface-container-lowest px-2 text-[13px] text-on-surface focus:outline-none"
                  />
                ) : (
                  <button
                    type="button"
                    onClick={() => onSeek(cue.start)}
                    className="min-w-0 text-left text-[13px] leading-5 text-on-surface"
                  >
                    <span className="mr-2 font-mono text-[10px] text-on-surface-variant">
                      {cue.speaker}
                    </span>
                    {cue.text}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    if (editing) commit(cue);
                    else startEditing(cue);
                  }}
                  aria-label={`${editing ? "Save" : "Edit"} caption ${index + 1} at ${formatMediaTime(
                    cue.start,
                  )}`}
                  className="grid size-7 place-items-center rounded-full text-on-surface-variant transition-colors duration-150 ease-standard hover:bg-surface-container-highest hover:text-on-surface"
                >
                  <Icon name={editing ? "check" : "edit"} size={14} />
                </button>
              </div>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
