import { formatMediaTime } from "../../lib/format";
import Icon from "../Icon";
import type { EditorTrack, ProcessingRun } from "./types";

interface TimelineProps {
  tracks: EditorTrack[];
  muted: Record<string, boolean>;
  onToggleMute: (id: string) => void;
  duration: number;
  currentTime: number;
  onSeek: (time: number) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  levels: { left: number; right: number };
  processing: ProcessingRun[];
}

const TRACK_OFFSET = 36;

function meterDb(level: number): string {
  if (level <= 0.001) return "−∞";
  return Math.max(-48, 20 * Math.log10(level)).toFixed(0);
}

export default function Timeline({
  tracks,
  muted,
  onToggleMute,
  duration,
  currentTime,
  onSeek,
  isPlaying,
  onTogglePlay,
  levels,
  processing,
}: TimelineProps) {
  const percent =
    duration > 0 ? Math.max(0, Math.min(100, (currentTime / duration) * 100)) : 0;

  function handleSeek(event: React.MouseEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const usable = Math.max(1, rect.width - TRACK_OFFSET);
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left - TRACK_OFFSET) / usable));
    onSeek(ratio * duration);
  }

  return (
    <section className="rounded-xl border border-outline-variant bg-surface-container p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onTogglePlay}
            aria-label={isPlaying ? "Pause" : "Play"}
            className="grid size-10 place-items-center rounded-full bg-primary text-on-primary transition-opacity duration-150 ease-standard hover:opacity-90"
          >
            <Icon name={isPlaying ? "pause" : "play_arrow"} size={20} />
          </button>
          <span className="font-mono text-[12px] text-on-surface">
            {formatMediaTime(currentTime)} / {formatMediaTime(duration)}
          </span>
        </div>
        <p className="text-[12px] text-on-surface-variant">
          Click the tracks to seek. Mute one layer to hear another.
        </p>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_64px]">
        <div>
          <div
            className="flex justify-between border-b border-outline-variant pb-1 font-mono text-[10px] text-on-surface-variant"
            style={{ paddingLeft: TRACK_OFFSET }}
          >
            {[0, 0.25, 0.5, 0.75, 1].map((position) => (
              <span key={position}>{formatMediaTime(duration * position)}</span>
            ))}
          </div>

          <div className="relative mt-2 cursor-crosshair" onClick={handleSeek}>
            {tracks.map((track, index) => {
              const groupChanged =
                index === 0 || tracks[index - 1].group !== track.group;
              const isMuted = Boolean(muted[track.id]);
              return (
                <div key={track.id}>
                  {groupChanged ? (
                    <p className="mb-1 mt-3 text-[10px] font-medium uppercase tracking-[0.08em] text-on-surface-variant">
                      {track.group}
                    </p>
                  ) : null}
                  <div className="flex items-center gap-2 py-1">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onToggleMute(track.id);
                      }}
                      aria-label={`${isMuted ? "Unmute" : "Mute"} ${track.label}`}
                      className="grid size-7 shrink-0 place-items-center rounded-full text-on-surface-variant transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface"
                    >
                      <Icon
                        name={isMuted ? "volume_off" : "volume_up"}
                        size={15}
                      />
                    </button>
                    <div
                      className={`flex h-9 min-w-0 flex-1 items-center justify-between gap-2 rounded border px-2 ${
                        isMuted
                          ? "border-outline-variant bg-surface-container-low opacity-45"
                          : "border-outline bg-surface-container-high"
                      }`}
                    >
                      <span className="truncate text-[12px] font-medium text-on-surface">
                        {track.label}
                      </span>
                      {track.artifact ? (
                        <a
                          href={track.artifact.download_url}
                          download
                          onClick={(event) => event.stopPropagation()}
                          aria-label={`Download ${track.label}`}
                          className="shrink-0 text-on-surface-variant transition-colors duration-150 ease-standard hover:text-on-surface"
                        >
                          <Icon name="download" size={14} />
                        </a>
                      ) : null}
                    </div>
                  </div>
                </div>
              );
            })}

            {processing.map((run) => (
              <div key={run.id} className="flex items-center gap-2 py-1">
                <span className="grid size-7 shrink-0 place-items-center">
                  <span className="spinner" aria-hidden="true" />
                </span>
                <div className="flex h-9 flex-1 items-center rounded border border-dashed border-outline-variant bg-surface-container-low px-2 text-[12px] text-on-surface-variant">
                  Processing {run.label}
                </div>
              </div>
            ))}

            <div
              className="pointer-events-none absolute bottom-0 top-0 w-px bg-primary"
              style={{
                left: `calc(${percent}% + ${TRACK_OFFSET * (1 - percent / 100)}px)`,
              }}
            >
              <span className="absolute -left-1.5 -top-1.5 size-3 rotate-45 border border-primary bg-surface" />
            </div>
          </div>
        </div>

        <div className="flex flex-col items-center gap-2 border-l border-outline-variant pl-4">
          <span className="text-[10px] uppercase tracking-[0.08em] text-on-surface-variant">
            Out
          </span>
          <div className="flex h-44 items-end gap-1.5">
            {[levels.left, levels.right].map((level, index) => (
              <div
                key={index}
                className="flex h-full w-3 items-end overflow-hidden rounded-sm bg-surface-container-highest"
              >
                <div
                  className="w-full rounded-sm bg-primary transition-[height] duration-75"
                  style={{ height: `${Math.max(3, level * 100)}%` }}
                />
              </div>
            ))}
          </div>
          <span className="font-mono text-[10px] text-on-surface-variant">
            L R
          </span>
          <span className="font-mono text-[10px] text-on-surface">
            {meterDb(Math.max(levels.left, levels.right))} dB
          </span>
        </div>
      </div>
    </section>
  );
}
