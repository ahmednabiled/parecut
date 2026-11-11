import { useCallback, useEffect, useRef, useState } from "react";
import { formatMediaTime } from "../../lib/format";
import Icon from "../Icon";
import type { EditorTrack, ProcessingRun } from "./types";

interface TimelineProps {
  tracks: EditorTrack[];
  muted: Record<string, boolean>;
  onToggleMute: (id: string) => void;
  duration: number;
  currentTime: number;
  getCurrentTime: () => number;
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

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest("button,a,input,select")) return;
    const time = timeAt(event.clientX);
    if (time === null) return;

    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    scrubbingRef.current = true;
    setScrubbing(true);
    onSeek(time);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!scrubbingRef.current) return;
    const target = timeAt(event.clientX);
    if (target !== null) onSeek(target);
  }

  function endScrub(event: React.PointerEvent<HTMLDivElement>) {
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
            className="grid size-10 place-items-center rounded-full bg-primary text-on-primary transition-opacity duration-150 ease-standard hover:opacity-90"
          >
            <Icon name={isPlaying ? "pause" : "play_arrow"} size={20} />
          </button>
          <span className="font-mono text-[12px] text-on-surface">
            {formatMediaTime(currentTime)} / {formatMediaTime(duration)}
          </span>
        </div>
        <p className="text-[12px] text-on-surface-variant">
          Drag the tracks to scrub. Mute one layer to hear another.
        </p>
      </div>

      <div className="mt-5 grid min-h-0 gap-4 overscroll-contain lg:grid-cols-[minmax(0,1fr)_64px] xl:flex-1 xl:overflow-y-auto xl:pr-1">
        <div>
          <div
            className="flex justify-between border-b border-outline-variant pb-1 font-mono text-[10px] text-on-surface-variant"
            style={{ paddingLeft: TRACK_OFFSET }}
          >
            {[0, 0.25, 0.5, 0.75, 1].map((position) => (
              <span key={position}>{formatMediaTime(duration * position)}</span>
            ))}
          </div>

          <div
            ref={laneRef}
            className={`relative mt-2 touch-none select-none ${
              scrubbing ? "cursor-grabbing" : "cursor-crosshair"
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
              ref={playheadRef}
              className="pointer-events-none absolute bottom-0 top-0 w-px will-change-[left] bg-primary"
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
