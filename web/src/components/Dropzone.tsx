import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { UPLOAD_ACCEPT } from "../lib/audio";
import { formatDuration, formatFileSize } from "../lib/format";
import Icon from "./Icon";

interface DropzoneProps {
  file: File | null;
  duration: number | null;
  progress: number | null;
  uploaded?: boolean;
  saving?: boolean;
  disabled?: boolean;
  error?: string | null;
  onSelect: (file: File) => void;
  onClear: () => void;
}

export default function Dropzone({
  file,
  duration,
  progress,
  uploaded = false,
  saving = false,
  disabled = false,
  error = null,
  onSelect,
  onClear,
}: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function browse() {
    inputRef.current?.click();
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0];
    event.target.value = "";
    if (next) onSelect(next);
  }

  function handleDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;
    const next = event.dataTransfer.files?.[0];
    if (next) onSelect(next);
  }

  const isVideo = file?.type.startsWith("video/") ?? false;
  const uploading = progress !== null && progress < 100;
  const uploadPercent = progress ?? 0;

  return (
    <div>
      <input
        ref={inputRef}
        id="source-file"
        type="file"
        accept={UPLOAD_ACCEPT}
        aria-label="Source media file"
        disabled={disabled}
        onChange={handleChange}
        className="sr-only"
      />

      {file ? (
        <div className="rounded-xl border border-outline-variant bg-surface-container-low p-5">
          <div className="flex items-start gap-4">
            <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-surface-container-high text-on-surface">
              <Icon name={isVideo ? "movie" : "audio_file"} size={20} />
            </div>

            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-on-surface">
                {file.name}
              </p>
              <p className="mt-1 font-mono text-[12px] text-on-surface-variant">
                {formatFileSize(file.size)}
                {" · "}
                {duration === null
                  ? "Duration read on the server"
                  : formatDuration(duration)}
              </p>

              {uploading ? (
                <div className="mt-3">
                  <div
                    role="progressbar"
                    aria-label="Upload progress"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={uploadPercent}
                    className="h-1 overflow-hidden rounded-full bg-surface-container-highest"
                  >
                    <div
                      className="h-full origin-left bg-primary transition-transform duration-150 ease-standard"
                      style={{ transform: `scaleX(${uploadPercent / 100})` }}
                    />
                  </div>
                  <p className="mt-2 font-mono text-[12px] text-on-surface-variant">
                    Uploading {uploadPercent}%
                  </p>
                </div>
              ) : saving ? (
                <div className="mt-3">
                  <div
                    role="progressbar"
                    aria-label="Saving upload"
                    aria-valuetext="Saving to storage"
                    className="h-1 overflow-hidden rounded-full bg-surface-container-highest"
                  >
                    <div className="h-full w-1/3 animate-pulse rounded-full bg-primary" />
                  </div>
                  <p className="mt-2 text-[12px] text-on-surface-variant">
                    Saving to storage… large files can take a few minutes.
                  </p>
                </div>
              ) : uploaded ? (
                <p className="mt-2 text-[12px] text-on-surface-variant">Uploaded</p>
              ) : null}
            </div>

            <button
              type="button"
              onClick={onClear}
              disabled={disabled}
              aria-label="Remove file"
              className="rounded-full p-2 text-on-surface-variant transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Icon name="close" size={18} />
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={browse}
          disabled={disabled}
          onDragOver={(event) => {
            event.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={`flex w-full flex-col items-center justify-center rounded-xl border border-dashed px-6 py-10 text-center transition-colors duration-150 ease-standard disabled:cursor-not-allowed disabled:opacity-50 ${
            dragging
              ? "border-on-surface bg-surface-container-high"
              : "border-outline-variant bg-surface-container-low hover:border-outline hover:bg-surface-container"
          }`}
        >
          <Icon name="upload" size={22} className="text-on-surface-variant" />
          <span className="mt-3 text-sm font-medium text-on-surface">
            Drop audio or video here
          </span>
          <span className="mt-1 text-[13px] text-on-surface-variant">
            or click to browse
          </span>
          <span className="mt-4 max-w-[46ch] text-[12px] leading-5 text-on-surface-variant">
            WAV, FLAC, MP3, M4A, AAC, OGG, MP4, MOV, MKV, or WebM. Up to 2 GB.
          </span>
        </button>
      )}

      {error ? (
        <p
          role="alert"
          className="mt-3 rounded-lg border border-error/25 bg-error-container px-4 py-3 text-sm text-on-error-container"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
