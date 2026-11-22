import { describe, expect, it } from "vitest";
import {
  chunkCaptions,
  cueAt,
  cuesToSrt,
  formatSrtTime,
  parseTranscript,
} from "./captions";

const before = JSON.stringify({
  speakers: ["SPEAKER_00"],
  segments: [
    {
      speaker: "SPEAKER_00",
      start: 1,
      end: 3,
      text: "one two three four five six",
    },
  ],
});

const after = JSON.stringify({
  segments: [
    {
      speaker: "SPEAKER_01",
      source_start: 2,
      source_end: 5,
      text: "a b c",
    },
  ],
});

describe("caption helpers", () => {
  it("parses before and after transcripts with source timecodes", () => {
    expect(parseTranscript(before)).toEqual([
      {
        speaker: "SPEAKER_00",
        start: 1,
        end: 3,
        text: "one two three four five six",
      },
    ]);
    expect(parseTranscript(after)).toEqual([
      { speaker: "SPEAKER_01", start: 2, end: 5, text: "a b c" },
    ]);
  });

  it("chunks captions by word count with proportional timing", () => {
    const cues = chunkCaptions(parseTranscript(before), 3);
    expect(cues).toHaveLength(2);
    expect(cues[0].text).toBe("one two three");
    expect(cues[0].start).toBe(1);
    expect(cues[0].end).toBe(2);
    expect(cues[1].text).toBe("four five six");
    expect(cues[1].end).toBe(3);
    expect(cueAt(cues, 2.4)?.text).toBe("four five six");
  });

  it("renders SRT with millisecond timecodes", () => {
    expect(formatSrtTime(65.5)).toBe("00:01:05,500");
    expect(cuesToSrt(chunkCaptions(parseTranscript(after), 2))).toContain(
      "00:00:02,000 --> 00:00:04,000",
    );
  });

  it("keeps corrected cue text without speaker prefixes in the SRT output", () => {
    const cues = chunkCaptions(parseTranscript(before), 3);
    const edited = cues.map((cue, index) =>
      index === 0 ? { ...cue, text: "corrected line" } : cue,
    );
    const srt = cuesToSrt(edited);
    expect(srt).toContain("00:00:01,000 --> 00:00:02,000\ncorrected line");
    expect(srt).not.toContain("[SPEAKER_00]");
    expect(srt).not.toContain("one two three");
  });

  it("uses exact per-word timestamps and splits on pauses when words are present", () => {
    const timed = JSON.stringify({
      speakers: ["SPEAKER_01"],
      segments: [
        {
          speaker: "SPEAKER_01",
          start: 1.0,
          end: 6.0,
          text: "fast words then after pause",
          words: [
            { start: 1.0, end: 1.2, text: "fast" },
            { start: 1.2, end: 1.5, text: "words" },
            { start: 1.5, end: 1.8, text: "then" },
            { start: 5.0, end: 5.4, text: "after" },
            { start: 5.4, end: 6.0, text: "pause" },
          ],
        },
      ],
    });

    const cues = chunkCaptions(parseTranscript(timed), 5);
    expect(cues).toHaveLength(2);
    expect(cues[0]).toEqual({
      speaker: "SPEAKER_01",
      start: 1.0,
      end: 1.8,
      text: "fast words then",
    });
    expect(cues[1]).toEqual({
      speaker: "SPEAKER_01",
      start: 5.0,
      end: 6.0,
      text: "after pause",
    });
  });
});
