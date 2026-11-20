import { useCallback, useEffect, useRef, useState } from "react";

export interface TimelineTrack {
  id: string;
  label: string;
  src: string;
  kind: "original" | "audio";
}

interface Levels {
  left: number;
  right: number;
}

export function useTimelineAudio(
  tracks: TimelineTrack[],
  muted: Record<string, boolean>,
  duration: number,
) {
  const elements = useRef(new Map<string, HTMLAudioElement>());
  const refCallbacks = useRef(
    new Map<string, (element: HTMLAudioElement | null) => void>(),
  );
  const contextRef = useRef<AudioContext | null>(null);
  const sourcesRef = useRef(new Map<string, MediaElementAudioSourceNode>());
  const gainsRef = useRef(new Map<string, GainNode>());
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const masterRef = useRef<HTMLAudioElement | null>(null);
  const timeRef = useRef(0);
  const lastUiRef = useRef(0);
  const seekTargetRef = useRef<number | null>(null);
  const seekStartedRef = useRef(0);
  const lastResyncRef = useRef(new Map<string, number>());
  const mutedRef = useRef(muted);
  const isPlayingRef = useRef(false);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [levels, setLevels] = useState<Levels>({ left: 0, right: 0 });

  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  const tracksKey = tracks.map((track) => track.id).join("|");

  const registerTrack = useCallback((id: string) => {
    let callback = refCallbacks.current.get(id);
    if (!callback) {
      callback = (element: HTMLAudioElement | null) => {
        if (element) {
          element.dataset.trackId = id;
          elements.current.set(id, element);
          return;
        }
        elements.current.delete(id);
        const source = sourcesRef.current.get(id);
        if (source) {
          try {
            source.disconnect();
          } catch {
            // Already disconnected.
          }
          sourcesRef.current.delete(id);
        }
        const gain = gainsRef.current.get(id);
        if (gain) {
          try {
            gain.disconnect();
          } catch {
            // Already disconnected.
          }
          gainsRef.current.delete(id);
        }
      };
      refCallbacks.current.set(id, callback);
    }
    return callback;
  }, []);

  const pause = useCallback(() => {
    for (const element of elements.current.values()) {
      element.pause();
    }
    const master = masterRef.current;
    if (master) {
      timeRef.current = master.currentTime;
      setCurrentTime(master.currentTime);
    }
    setIsPlaying(false);
    setLevels({ left: 0, right: 0 });
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const tick = useCallback(function tick() {
    const master = masterRef.current;
    if (master) {
      const seekTarget = seekTargetRef.current;
      let displayTime = master.currentTime;

      if (seekTarget !== null) {
        const elapsed = performance.now() - seekStartedRef.current;
        if (
          (!master.seeking && Math.abs(master.currentTime - seekTarget) < 0.5) ||
          elapsed > 700
        ) {
          seekTargetRef.current = null;
        } else {
          displayTime = seekTarget;
        }
      } else if (!master.paused) {
        const nowMs = performance.now();
        for (const [id, element] of elements.current.entries()) {
          if (element === master || element.seeking || element.ended) {
            continue;
          }
          if (element.paused) {
            if (element.readyState >= 2) {
              const last = lastResyncRef.current.get(id) ?? 0;
              if (nowMs - last > 500) {
                lastResyncRef.current.set(id, nowMs);
                try {
                  element.currentTime = Math.min(
                    master.currentTime,
                    element.duration || master.currentTime,
                  );
                } catch {
                  // Element may not be seekable yet.
                }
                void element.play().catch(() => undefined);
              }
            }
            continue;
          }
          if (Math.abs(element.currentTime - master.currentTime) <= 0.15) {
            continue;
          }
          const last = lastResyncRef.current.get(id) ?? 0;
          if (nowMs - last < 600) {
            continue;
          }
          lastResyncRef.current.set(id, nowMs);
          try {
            element.currentTime = Math.min(
              master.currentTime,
              element.duration || master.currentTime,
            );
          } catch {
            // The element may not be seekable yet.
          }
        }
      }

      timeRef.current = displayTime;
      if (master.ended) {
        pause();
        return;
      }
    }

    const now = performance.now();
    if (now - lastUiRef.current >= 60) {
      lastUiRef.current = now;
      setCurrentTime(timeRef.current);

      const analyser = analyserRef.current;
      if (analyser) {
        const data = new Uint8Array(analyser.fftSize);
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        let peak = 0;
        for (const value of data) {
          const sample = (value - 128) / 128;
          sum += sample * sample;
          peak = Math.max(peak, Math.abs(sample));
        }
        const rms = Math.sqrt(sum / data.length);
        const level = Math.min(1, Math.max(rms * 2.4, peak * 0.6));
        setLevels({ left: level, right: level });
      }
    }

    rafRef.current = requestAnimationFrame(tick);
  }, [pause]);

  const ensureGraph = useCallback(() => {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Ctor) return null;

    if (contextRef.current === null) {
      const context = new Ctor();
      const analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = 0.7;
      analyser.connect(context.destination);
      contextRef.current = context;
      analyserRef.current = analyser;
    }

    const context = contextRef.current;
    for (const [id, element] of elements.current) {
      if (!sourcesRef.current.has(id)) {
        try {
          const source = context.createMediaElementSource(element);
          const gain = context.createGain();
          source.connect(gain);
          gain.connect(analyserRef.current as AnalyserNode);
          sourcesRef.current.set(id, source);
          gainsRef.current.set(id, gain);
        } catch {
          // A media element can only be connected once; ignore failures.
        }
      }
      const gain = gainsRef.current.get(id);
      if (gain) gain.gain.value = mutedRef.current[id] ? 0 : 1;
      element.muted = false;
      element.volume = 1;
    }
    return context;
  }, []);

  const play = useCallback(async () => {
    const context = ensureGraph();
    const entries = Array.from(elements.current.entries());
    if (entries.length === 0) return;

    const master = masterRef.current;
    const target = master
      ? master.ended
        ? 0
        : master.currentTime
      : currentTime;
    for (const [id, element] of entries) {
      if (Math.abs(element.currentTime - target) > 0.15) {
        try {
          element.currentTime = Math.min(target, element.duration || target);
        } catch {
          // Some browsers reject seeking before metadata is ready.
        }
      }
      if (context) {
        element.muted = false;
      } else {
        element.muted = muted[id] ?? false;
      }
    }

    if (context) await context.resume();
    await Promise.all(
      entries.map(([, element]) => element.play().catch(() => undefined)),
    );
    const masterElement = master ?? entries[0][1];
    const syncTime = masterElement.currentTime;
    for (const [, element] of entries) {
      if (element === masterElement) continue;
      if (Math.abs(element.currentTime - syncTime) > 0.08) {
        try {
          element.currentTime = syncTime;
        } catch {
          // Ignore elements that are not seekable yet.
        }
      }
    }
    setIsPlaying(true);
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(tick);
  }, [currentTime, ensureGraph, muted, tick]);

  const seek = useCallback(
    (time: number) => {
      const target = Math.max(0, Math.min(duration, time));
      seekTargetRef.current = target;
      seekStartedRef.current = performance.now();
      timeRef.current = target;
      for (const element of elements.current.values()) {
        try {
          element.currentTime = Math.min(target, element.duration || target);
        } catch {
          // Ignore seeks before metadata is ready.
        }
      }
      setCurrentTime(target);
    },
    [duration],
  );

  const toggle = useCallback(() => {
    if (isPlaying) pause();
    else void play();
  }, [isPlaying, pause, play]);

  const getCurrentTime = useCallback(() => timeRef.current, []);

  useEffect(() => {
    const original = elements.current.get("original");
    masterRef.current =
      original ?? Array.from(elements.current.values())[0] ?? null;
  }, [tracksKey]);

  useEffect(() => {
    if (!isPlaying) return;
    const context = ensureGraph();
    if (context && context.state === "suspended") {
      void context.resume().catch(() => undefined);
    }
    const master = masterRef.current;
    const cleanups: (() => void)[] = [];

    for (const element of elements.current.values()) {
      const syncAndPlay = () => {
        if (!isPlayingRef.current) return;
        try {
          if (master && element !== master) {
            element.currentTime = Math.min(
              master.currentTime,
              element.duration || master.currentTime,
            );
          }
        } catch {
          // The element may not be seekable yet.
        }
        void element.play().catch(() => undefined);
      };

      if (element.readyState < 1) {
        element.addEventListener("loadedmetadata", syncAndPlay, { once: true });
        cleanups.push(() =>
          element.removeEventListener("loadedmetadata", syncAndPlay),
        );
        continue;
      }

      if (element.paused && !element.ended) {
        syncAndPlay();
      }
    }

    return () => {
      for (const cleanup of cleanups) cleanup();
    };
  }, [tracksKey, isPlaying, ensureGraph]);

  useEffect(() => {
    for (const [id, gain] of gainsRef.current) {
      gain.gain.value = muted[id] ? 0 : 1;
    }
    if (!contextRef.current) {
      for (const [id, element] of elements.current) {
        element.muted = muted[id] ?? false;
      }
    }
  }, [muted]);

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      for (const element of elements.current.values()) element.pause();
      void contextRef.current?.close();
    };
  }, []);

  return {
    registerTrack,
    isPlaying,
    currentTime,
    levels,
    play,
    pause,
    seek,
    toggle,
    getCurrentTime,
  };
}
