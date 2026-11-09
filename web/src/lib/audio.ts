export const ALLOWED_UPLOAD_EXTENSIONS = [
  "wav",
  "flac",
  "mp3",
  "m4a",
  "aac",
  "ogg",
  "mp4",
  "mov",
  "mkv",
  "webm",
] as const;

export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024;

export const UPLOAD_ACCEPT = ALLOWED_UPLOAD_EXTENSIONS.map(
  (extension) => `.${extension}`,
).join(",");

const ALLOWED = new Set<string>(ALLOWED_UPLOAD_EXTENSIONS);

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index === -1 ? "" : name.slice(index + 1).toLowerCase();
}

export function validateUploadFile(file: File): string | null {
  const extension = extensionOf(file.name);
  if (!ALLOWED.has(extension)) {
    return `Unsupported file type: ${extension || "none"}`;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return "File exceeds the maximum upload size (2 GB).";
  }
  return null;
}

export function readAudioDuration(file: File): Promise<number | null> {
  if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") {
    return Promise.resolve(null);
  }

  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const audio = document.createElement("audio");
    let settled = false;
    let timer: number | undefined;

    const finish = (value: number | null) => {
      if (settled) return;
      settled = true;
      if (timer !== undefined) window.clearTimeout(timer);
      audio.onloadedmetadata = null;
      audio.onerror = null;
      audio.removeAttribute("src");
      URL.revokeObjectURL(url);
      resolve(value);
    };

    audio.preload = "metadata";
    audio.onloadedmetadata = () => {
      const duration = audio.duration;
      finish(Number.isFinite(duration) && duration > 0 ? duration : null);
    };
    audio.onerror = () => finish(null);
    timer = window.setTimeout(() => finish(null), 8000);
    audio.src = url;
  });
}
