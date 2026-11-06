import { describe, expect, it } from "vitest";
import { formatClock, formatDuration, formatFileSize } from "./format";

describe("format helpers", () => {
  it("formats clock time with milliseconds", () => {
    expect(formatClock(8.48)).toBe("00:00:08.480");
    expect(formatClock(3725.1)).toBe("01:02:05.100");
  });

  it("formats unknown durations and byte sizes", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatFileSize(1536)).toBe("1.5 KB");
  });
});
