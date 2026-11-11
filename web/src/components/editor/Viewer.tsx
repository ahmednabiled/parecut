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
    <section className="rounded-xl border border-outline-variant bg-surface-container p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-medium text-on-surface">Captions</h2>
          <p className="mt-1 text-[12px] text-on-surface-variant">
            Follows the playhead. Fix a line, then download the caption file.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label
            htmlFor="caption-chunk"
            className="text-[12px] text-on-surface-variant"
          >
            Words
          </label>
          <select
            id="caption-chunk"
            value={chunkWords}
            onChange={(event) => onChunkWords(Number(event.target.value))}
            className="h-8 rounded border border-outline bg-transparent px-2 text-[12px] text-on-surface"
          >
            <option value={3}>3</option>
            <option value={5}>5</option>
            <option value={8}>8</option>
          </select>
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

      <div className="mt-5 flex min-h-[210px] items-center justify-center rounded-lg border border-outline-variant bg-surface-container-lowest px-6 py-8 text-center">
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
        <div className="mt-4 max-h-56 space-y-1 overflow-y-auto pr-1">
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
