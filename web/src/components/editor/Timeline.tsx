import { useQueries } from "@tanstack/react-query";
import {
  memo,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { formatMediaTime } from "../../lib/format";
import Icon from "../Icon";
import type { EditorTrack, ProcessingRun } from "./types";

interface TimelineProps {
  tracks: EditorTrack[];
  muted: Record<string, boolean>;
  onToggleMute: (id: string) => void;
  autoSolo: boolean;
  onToggleAutoSolo: () => void;
  selectedTrackId: string;
  onSelectTrack: (id: string) => void;
  onDeleteTrack: (id: string) => void;
  deletingTrackId?: string | null;
  duration: number;
  currentTime: number;
  getCurrentTime: () => number;
  onSeek: (time: number) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  levels: { left: number; right: number };
  processing: ProcessingRun[];
}

interface PeaksResponse {
  peaks: number[];
}

const TRACK_OFFSET = 36;
const SELECTION_COLOR = "#8ec0ee";

interface TrackTone {
  wave: string;
  lane: string;
  border: string;
}

const TRACK_TONES: TrackTone[] = [
  {
    wave: "#c7d4df",
    lane: "rgba(199, 212, 223, 0.07)",
    border: "rgba(199, 212, 223, 0.3)",
  },
  {
    wave: "#c4d9cf",
    lane: "rgba(196, 217, 207, 0.07)",
    border: "rgba(196, 217, 207, 0.3)",
  },
  {
    wave: "#ded0b8",
    lane: "rgba(222, 208, 184, 0.07)",
    border: "rgba(222, 208, 184, 0.3)",
  },
  {
    wave: "#d8c7da",
    lane: "rgba(216, 199, 218, 0.07)",
    border: "rgba(216, 199, 218, 0.3)",
  },
  {
    wave: "#e0c7c1",
    lane: "rgba(224, 199, 193, 0.07)",
    border: "rgba(224, 199, 193, 0.3)",
  },
  {
    wave: "#cdd6c6",
    lane: "rgba(205, 214, 198, 0.07)",
    border: "rgba(205, 214, 198, 0.3)",
  },
];

function meterDb(level: number): string {
  if (level <= 0.001) return "−∞";
  return Math.max(-48, 20 * Math.log10(level)).toFixed(0);
}

const Waveform = memo(function Waveform({
  peaks,
  tone,
}: {
  peaks: number[];
  tone: TrackTone;
}) {
  if (peaks.length < 2) {
    return (
      <div
        className="absolute inset-x-0 top-1/2 h-px"
        style={{ backgroundColor: tone.border }}
      />
    );
  }

  const max = Math.max(1e-6, ...peaks);
  const count = peaks.length;
  let upper = "";
  let lower = "";

  for (let index = 0; index < count; index += 1) {
    const x = (index / (count - 1)) * 1000;
    const normalized = Math.pow(Math.min(1, peaks[index] / max), 0.72);
    const y = Math.max(0.7, normalized * 47);
    upper += `${index === 0 ? "M" : "L"}${x.toFixed(1)},${(50 - y).toFixed(1)} `;
  }
  for (let index = count - 1; index >= 0; index -= 1) {
    const x = (index / (count - 1)) * 1000;
    const normalized = Math.pow(Math.min(1, peaks[index] / max), 0.72);
    const y = Math.max(0.7, normalized * 47);
    lower += `L${x.toFixed(1)},${(50 + y).toFixed(1)} `;
  }

  return (
    <svg
      viewBox="0 0 1000 100"
      preserveAspectRatio="none"
      aria-hidden="true"
      className="absolute inset-0 h-full w-full"
      style={{ color: tone.wave }}
    >
      <path d={`${upper}${lower}Z`} fill="currentColor" />
    </svg>
  );
});

export default function Timeline({
  tracks,
  muted,
  onToggleMute,
  autoSolo,
  onToggleAutoSolo,
  selectedTrackId,
  onSelectTrack,
  onDeleteTrack,
  deletingTrackId = null,
  duration,
  currentTime,
  getCurrentTime,
  onSeek,
  isPlaying,
  onTogglePlay,
  levels,
  processing,
}: TimelineProps) {
  const laneRef = useRef<HTMLDivElement | null>(null);
  const playheadRef = useRef<HTMLDivElement | null>(null);
  const scrubbingRef = useRef(false);
  const [scrubbing, setScrubbing] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const peaksQueries = useQueries({
    queries: tracks.map((track) => ({
      queryKey: ["peaks", track.peaksSrc],
      queryFn: async () => {
        const response = await fetch(track.peaksSrc, {
          credentials: "include",
        });
        if (!response.ok) throw new Error("Waveform unavailable");
        return (await response.json()) as PeaksResponse;
      },
      staleTime: Infinity,
    })),
  });
  const peaks = tracks.map(
    (_track, index) => peaksQueries[index]?.data?.peaks ?? [],
  );

  const paintPlayhead = useCallback(() => {
    const element = playheadRef.current;
    if (!element) return;
    const time = getCurrentTime();
    const ratio =
      duration > 0 ? Math.max(0, Math.min(1, time / duration)) : 0;
    const percent = ratio * 100;
    element.style.left = `calc(${percent}% + ${
      TRACK_OFFSET * (1 - percent / 100)
    }px)`;
  }, [duration, getCurrentTime]);

  useEffect(() => {
    paintPlayhead();
    if (!isPlaying) return;
    let frame = 0;
    const loop = () => {
      paintPlayhead();
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [isPlaying, paintPlayhead]);

  useEffect(() => {
    if (!isPlaying) paintPlayhead();
  }, [currentTime, isPlaying, paintPlayhead]);

  function timeAt(clientX: number): number | null {
    const rect = laneRef.current?.getBoundingClientRect();
    if (!rect) return null;
    const usable = Math.max(1, rect.width - TRACK_OFFSET);
    const ratio = Math.max(
      0,
      Math.min(1, (clientX - rect.left - TRACK_OFFSET) / usable),
    );
    return ratio * duration;
  }

  function startScrub(
    event: React.PointerEvent<HTMLElement>,
    ignoreInteractive: boolean,
  ) {
    if (event.button !== 0) return;
    if (ignoreInteractive) {
      const target = event.target as HTMLElement;
      if (target.closest("button,a,input,select")) return;
    }
    const time = timeAt(event.clientX);
    if (time === null) return;

    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    scrubbingRef.current = true;
    setScrubbing(true);
    onSeek(time);
  }

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    startScrub(event, true);
  }

  function handleHandlePointerDown(event: React.PointerEvent<HTMLElement>) {
    startScrub(event, false);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLElement>) {
    if (!scrubbingRef.current) return;
    const target = timeAt(event.clientX);
    if (target !== null) onSeek(target);
  }

  function endScrub(event: React.PointerEvent<HTMLElement>) {
    if (!scrubbingRef.current) return;
    scrubbingRef.current = false;
    setScrubbing(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const target = timeAt(event.clientX);
    if (target !== null) onSeek(target);
  }

  return (
    <section className="rounded-xl border border-outline-variant bg-surface-container p-5 xl:flex xl:h-full xl:min-h-0 xl:flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onTogglePlay}
            aria-label={isPlaying ? "Pause" : "Play"}
            title="Play / Pause (Space)"
            className="grid size-10 place-items-center rounded-full bg-primary text-on-primary transition-opacity duration-150 ease-standard hover:opacity-90"
          >
            <Icon name={isPlaying ? "pause" : "play_arrow"} size={20} />
          </button>
          <span className="font-mono text-[12px] text-on-surface">
            {formatMediaTime(currentTime)} / {formatMediaTime(duration)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-[12px] text-on-surface-variant">
            Space to play. Drag playhead or waves to scrub.
          </p>
          <button
            type="button"
            role="switch"
            aria-checked={autoSolo}
            onClick={onToggleAutoSolo}
            title="Automatically mute other tracks when selecting a track"
            className={`inline-flex h-7 items-center gap-2 rounded-full border px-2.5 text-[11px] font-medium transition-colors duration-150 ease-standard ${
              autoSolo
                ? "border-primary bg-primary text-on-primary"
                : "border-outline-variant bg-surface-container-low text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
            }`}
          >
            <span
              aria-hidden="true"
              className={`size-1.5 rounded-full ${
                autoSolo ? "bg-on-primary" : "bg-on-surface-variant/60"
              }`}
            />
            Auto-solo
          </button>
        </div>
      </div>

      <div className="mt-4 flex min-h-0 gap-3 xl:flex-1">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div
            onPointerDown={handleHandlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={endScrub}
            onPointerCancel={endScrub}
            onLostPointerCapture={endScrub}
            className={`flex shrink-0 touch-none select-none justify-between border-b border-outline-variant pb-1 font-mono text-[10px] text-on-surface-variant ${
              scrubbing ? "cursor-grabbing" : "cursor-pointer"
            }`}
            style={{ paddingLeft: TRACK_OFFSET }}
          >
            {[0, 0.25, 0.5, 0.75, 1].map((position) => (
              <span key={position}>{formatMediaTime(duration * position)}</span>
            ))}
          </div>

          <div className="relative mt-2 h-[20rem] min-h-0 xl:h-auto xl:flex-1">
            <div
              ref={laneRef}
              className={`absolute inset-0 touch-none select-none overflow-y-auto overscroll-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ${
                scrubbing ? "cursor-grabbing" : "cursor-default"
              }`}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={endScrub}
              onPointerCancel={endScrub}
              onLostPointerCapture={endScrub}
            >
              {tracks.map((track, index) => {
                const groupChanged =
                  index === 0 || tracks[index - 1].group !== track.group;
                const isMuted = Boolean(muted[track.id]);
                const isSelected = selectedTrackId === track.id;
                const tone = TRACK_TONES[index % TRACK_TONES.length];
                return (
                  <div key={track.id}>
                    {groupChanged ? (
                      <div className="mb-1 mt-3 flex items-center gap-2 first:mt-0">
                        <span
                          className="size-1.5 rounded-full"
                          style={{ backgroundColor: tone.wave }}
                        />
                        <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-on-surface-variant">
                          {track.group}
                        </p>
                      </div>
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
                        className={`relative h-10 min-w-0 flex-1 overflow-hidden rounded border transition-[border-color] duration-150 ease-standard ${
                          isMuted && !isSelected ? "opacity-60" : ""
                        }`}
                        style={{
                          borderColor: isSelected
                            ? "transparent"
                            : tone.border,
                          backgroundColor: tone.lane,
                        }}
                      >
                        <Waveform peaks={peaks[index]} tone={tone} />
                        {isSelected ? (
                          <>
                            <span
                              className="pointer-events-none absolute inset-0"
                              style={{
                                backgroundColor: SELECTION_COLOR,
                                opacity: 0.08,
                              }}
                            />
                            <span
                              className="pointer-events-none absolute inset-0 rounded border-2"
                              style={{ borderColor: SELECTION_COLOR }}
                            />
                          </>
                        ) : null}
                        {peaks[index].length < 2 ? (
                          <div className="pointer-events-none absolute inset-0 grid place-items-center text-[11px] text-on-surface-variant">
                            {peaksQueries[index]?.isError ? (
                              <span>Waveform unavailable</span>
                            ) : (
                              <span className="flex items-center gap-2">
                                <span className="spinner" aria-hidden="true" />
                                Rendering waveform…
                              </span>
                            )}
                          </div>
                        ) : null}
                        <div className="pointer-events-none absolute inset-0 flex items-center justify-between gap-2 px-2">
                          <button
                            type="button"
                            onPointerDown={(event) => event.stopPropagation()}
                            onClick={(event) => {
                              event.stopPropagation();
                              onSelectTrack(track.id);
                            }}
                            aria-pressed={isSelected}
                            aria-label={`Use ${track.label} as the effect input`}
                            title="Effects apply to this track"
                            className={`pointer-events-auto max-w-[78%] rounded px-1.5 py-0.5 text-left text-[11px] font-medium transition-colors duration-150 ease-standard ${
                              isSelected
                                ? ""
                                : `bg-surface-container/90 hover:bg-surface-container-highest ${
                                    isMuted
                                      ? "text-on-surface-variant"
                                      : "text-on-surface"
                                  }`
                            }`}
                            style={
                              isSelected
                                ? {
                                    backgroundColor: SELECTION_COLOR,
                                    color: "#0b0b0b",
                                  }
                                : undefined
                            }
                          >
                            <span className="flex min-w-0 items-center gap-1.5">
                              {isSelected ? (
                                <span
                                  className="size-1.5 shrink-0 rounded-full bg-current"
                                  aria-hidden="true"
                                />
                              ) : null}
                              <span className="truncate">{track.label}</span>
                            </span>
                          </button>
                          {track.artifact ? (
                            <span className="pointer-events-auto flex shrink-0 items-center gap-0.5 rounded-md border border-outline-variant/80 bg-surface-container/95 px-1 py-0.5 shadow-sm backdrop-blur-[2px]">
                              {pendingDelete === track.id ? (
                                <>
                                  <span className="px-1 text-[10px] font-medium text-error">
                                    Delete?
                                  </span>
                                  <button
                                    type="button"
                                    onPointerDown={(event) =>
                                      event.stopPropagation()
                                    }
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      setPendingDelete(null);
                                      onDeleteTrack(track.id);
                                    }}
                                    aria-label={`Confirm deleting ${track.label}`}
                                    className="grid size-5 place-items-center rounded text-error transition-colors duration-150 ease-standard hover:bg-error-container"
                                  >
                                    <Icon name="check" size={14} />
                                  </button>
                                  <button
                                    type="button"
                                    onPointerDown={(event) =>
                                      event.stopPropagation()
                                    }
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      setPendingDelete(null);
                                    }}
                                    aria-label="Cancel delete"
                                    className="grid size-5 place-items-center rounded text-on-surface/80 transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface"
                                  >
                                    <Icon name="close" size={14} />
                                  </button>
                                </>
                              ) : (
                                <>
                                  <a
                                    href={track.artifact.download_url}
                                    download
                                    onPointerDown={(event) =>
                                      event.stopPropagation()
                                    }
                                    onClick={(event) => event.stopPropagation()}
                                    aria-label={`Download ${track.label}`}
                                    title="Download track"
                                    className="grid size-5 place-items-center rounded text-on-surface/85 transition-colors duration-150 ease-standard hover:bg-surface-container-highest hover:text-on-surface"
                                  >
                                    <Icon name="download" size={14} />
                                  </a>
                                  <button
                                    type="button"
                                    disabled={deletingTrackId === track.id}
                                    onPointerDown={(event) =>
                                      event.stopPropagation()
                                    }
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      setPendingDelete(track.id);
                                    }}
                                    aria-label={`Delete ${track.label}`}
                                    title="Delete track"
                                    className="grid size-5 place-items-center rounded text-on-surface/85 transition-colors duration-150 ease-standard hover:bg-error-container hover:text-error disabled:opacity-60"
                                  >
                                    <span className="grid size-3.5 place-items-center">
                                      {deletingTrackId === track.id ? (
                                        <span
                                          className="spinner"
                                          aria-hidden="true"
                                        />
                                      ) : (
                                        <Icon name="delete" size={14} />
                                      )}
                                    </span>
                                  </button>
                                </>
                              )}
                            </span>
                          ) : null}
                        </div>
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
                  <div className="relative flex h-10 flex-1 items-center justify-between overflow-hidden rounded border border-dashed border-outline-variant bg-surface-container-low px-2 text-[12px] text-on-surface-variant">
                    {typeof run.percent === "number" && run.percent > 0 ? (
                      <span
                        aria-hidden="true"
                        className="pointer-events-none absolute inset-y-0 left-0 bg-primary/10 transition-[width] duration-300"
                        style={{
                          width: `${Math.max(0, Math.min(100, run.percent))}%`,
                        }}
                      />
                    ) : null}
                    <span className="relative">Processing {run.label}</span>
                    {typeof run.percent === "number" ? (
                      <span className="relative font-mono text-[11px] text-on-surface-variant">
                        {run.percent}%
                      </span>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>

            <div
              ref={playheadRef}
              className="pointer-events-none absolute -top-2 bottom-0 -ml-[5px] w-[11px] will-change-[left]"
            >
              <div
                role="slider"
                aria-label="Playhead"
                aria-valuemin={0}
                aria-valuemax={Math.round(duration)}
                aria-valuenow={Math.round(currentTime)}
                onPointerDown={handleHandlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={endScrub}
                onPointerCancel={endScrub}
                onLostPointerCapture={endScrub}
                className={`pointer-events-auto -mx-1 -mt-1 flex touch-none justify-center px-1 pb-1 pt-1 ${
                  scrubbing ? "cursor-grabbing" : "cursor-grab"
                }`}
              >
                <svg
                  width="11"
                  height="8"
                  viewBox="0 0 11 8"
                  aria-hidden="true"
                  className="block shrink-0 text-primary"
                >
                  <polygon points="0,0 11,0 5.5,8" fill="currentColor" />
                </svg>
              </div>
              <span className="absolute bottom-0 left-[5px] top-[7px] w-px bg-primary" />
            </div>
          </div>
        </div>

        <div className="flex w-14 shrink-0 flex-col items-center gap-2 border-l border-outline-variant pl-3">
          <span className="text-[10px] uppercase tracking-[0.08em] text-on-surface-variant">
            Out
          </span>
          <div className="flex min-h-0 flex-1 items-end justify-center gap-1.5 py-1">
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
