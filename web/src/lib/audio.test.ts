import { describe, expect, it } from "vitest";
import { MAX_UPLOAD_BYTES, validateUploadFile } from "./audio";

describe("validateUploadFile", () => {
  it("rejects unsupported extensions", () => {
    expect(validateUploadFile(new File(["x"], "notes.txt"))).toBe(
      "Unsupported file type: txt",
    );
  });

  it("accepts supported audio and video extensions", () => {
    expect(validateUploadFile(new File(["x"], "take.WAV"))).toBeNull();
    expect(validateUploadFile(new File(["x"], "take.mp4"))).toBeNull();
  });

  it("rejects files above the upload limit", () => {
    const file = new File(["x"], "take.wav");
    Object.defineProperty(file, "size", { value: MAX_UPLOAD_BYTES + 1 });

    expect(validateUploadFile(file)).toMatch(/maximum upload size/);
  });
});
