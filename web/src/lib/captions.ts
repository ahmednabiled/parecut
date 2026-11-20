export interface CaptionSegment {
  speaker: string;
  start: number;
  end: number;
  text: string;
}

export interface CaptionCue {
  speaker: string;
  start: number;
  end: number;
  text: string;
}

interface RawSegment {
  speaker?: unknown;
  text?: unknown;
  start?: unknown;
  end?: unknown;
  source_start?: unknown;
  source_end?: unknown;
}

interface RawTranscript {
  segments?: unknown;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function parseTranscript(raw: string): CaptionSegment[] {
  let data: RawTranscript;
  try {
    data = JSON.parse(raw) as RawTranscript;
  } catch {
    return [];
  }
  if (!Array.isArray(data.segments)) {
    return [];
  }

  const segments: CaptionSegment[] = [];
  for (const value of data.segments) {
    if (value === null || typeof value !== "object") continue;
    const rawSegment = value as RawSegment;
    const start =
      numberOrNull(rawSegment.source_start) ?? numberOrNull(rawSegment.start);
    const end =
      numberOrNull(rawSegment.source_end) ?? numberOrNull(rawSegment.end);
    const text =
      typeof rawSegment.text === "string" ? rawSegment.text.trim() : "";
    if (start === null || end === null || end <= start || !text) continue;
    const speaker =
      typeof rawSegment.speaker === "string" && rawSegment.speaker
        ? rawSegment.speaker
        : "SPEAKER_01";
    segments.push({ speaker, start, end, text });
  }

  return segments.sort((a, b) => a.start - b.start);
}

export function chunkCaptions(
  segments: CaptionSegment[],
  wordsPerCue: number,
): CaptionCue[] {
  const size = Math.max(1, Math.min(12, Math.round(wordsPerCue)));
  const cues: CaptionCue[] = [];

  for (const segment of segments) {
    const words = segment.text.split(/\s+/).filter(Boolean);
    if (words.length === 0) continue;
    const duration = Math.max(0.001, segment.end - segment.start);
    let wordIndex = 0;

    while (wordIndex < words.length) {
      const chunk = words.slice(wordIndex, wordIndex + size);
      const startIndex = wordIndex;
      wordIndex += chunk.length;
      cues.push({
        speaker: segment.speaker,
        start: segment.start + (duration * startIndex) / words.length,
        end: segment.start + (duration * wordIndex) / words.length,
        text: chunk.join(" "),
      });
    }
  }

  return cues;
}

export function cueAt(cues: CaptionCue[], time: number): CaptionCue | null {
  for (const cue of cues) {
    if (time >= cue.start && time < cue.end) return cue;
  }
  return null;
}

export function captionCueKey(cue: CaptionCue): string {
  return `${cue.speaker}|${cue.start.toFixed(2)}|${cue.end.toFixed(2)}`;
}

export function formatSrtTime(seconds: number): string {
  const totalMs = Math.max(0, Math.round(seconds * 1000));
  const hours = Math.floor(totalMs / 3_600_000);
  const minutes = Math.floor((totalMs % 3_600_000) / 60_000);
  const secs = Math.floor((totalMs % 60_000) / 1000);
  const millis = totalMs % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(
    secs,
  ).padStart(2, "0")},${String(millis).padStart(3, "0")}`;
}

export function cuesToSrt(cues: CaptionCue[]): string {
  return cues
    .map(
      (cue, index) =>
        `${index + 1}\n${formatSrtTime(cue.start)} --> ${formatSrtTime(cue.end)}\n${cue.text}`,
    )
    .join("\n\n");
}

export function cuesToVtt(cues: CaptionCue[]): string {
  return (
    "WEBVTT\n\n" +
    cues
      .map(
        (cue) =>
          `${formatSrtTime(cue.start).replace(",", ".")} --> ${formatSrtTime(cue.end).replace(",", ".")}\n${cue.text}`,
      )
      .join("\n\n")
  );
}
