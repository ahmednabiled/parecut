import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, apiFetch } from "../api/client";
import type {
  Job,
  PipelineConfig,
  PresignResponse,
  ProfileResponse,
} from "../api/types";
import Dropzone from "../components/Dropzone";
import Panel from "../components/Panel";
import PipelineToggles from "../components/PipelineToggles";
import { readAudioDuration, validateUploadFile } from "../lib/audio";
import { estimateCredits, validatePipeline } from "../lib/credits";
import { formatDuration } from "../lib/format";

const FPS_OPTIONS = ["24", "25", "29.97", "30", "60"];

const DEFAULT_PIPELINE: PipelineConfig = {
  noise_reduction: true,
  enhance: true,
  enhance_mix: 0.8,
  separate_music: true,
  separate_speakers: true,
  transcribe: true,
  rough_cut: true,
};

const fieldClass =
  "h-12 w-full rounded border border-outline bg-transparent px-4 text-[15px] text-on-surface transition-[border-color,background-color] duration-150 ease-standard hover:border-on-surface-variant focus:border-on-surface";

function putFile(
  xhr: XMLHttpRequest,
  url: string,
  file: File,
  onProgress: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    xhr.open("PUT", url);
    try {
      xhr.withCredentials =
        new URL(url, window.location.href).origin === window.location.origin;
    } catch {
      xhr.withCredentials = false;
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
        return;
      }
      let detail = `Upload failed (${xhr.status}).`;
      try {
        const body = JSON.parse(xhr.responseText) as { detail?: unknown };
        if (typeof body.detail === "string") {
          detail = body.detail;
        }
      } catch {
        // keep the generic message
      }
      reject(new Error(detail));
    };
    xhr.onerror = () =>
      reject(new Error("Upload failed. Check your connection and try again."));
    xhr.onabort = () => reject(new Error("Upload canceled."));

    xhr.setRequestHeader(
      "Content-Type",
      file.type || "application/octet-stream",
    );
    xhr.send(file);
  });
}

interface Shortfall {
  required: number;
  available: number;
}

export default function NewJob() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const profileQuery = useQuery<ProfileResponse>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileResponse>("/api/profile"),
  });

  const [file, setFile] = useState<File | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [config, setConfig] = useState<PipelineConfig>(DEFAULT_PIPELINE);
  const [fps, setFps] = useState("25");
  const [progress, setProgress] = useState<number | null>(null);
  const [uploadKey, setUploadKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [shortfall, setShortfall] = useState<Shortfall | null>(null);

  const hydrated = useRef(false);
  const selectionId = useRef(0);
  const uploadId = useRef(0);
  const xhrRef = useRef<XMLHttpRequest | null>(null);

  useEffect(() => {
    const data = profileQuery.data;
    if (!data || hydrated.current) return;
    hydrated.current = true;
    setFps(data.profile.default_fps);
    setConfig((current) => ({
      ...current,
      enhance_mix: data.profile.default_enhance_mix / 100,
    }));
  }, [profileQuery.data]);

  useEffect(() => {
    return () => {
      uploadId.current += 1;
      xhrRef.current?.abort();
    };
  }, []);

  async function beginUpload(nextFile: File) {
    const id = ++uploadId.current;
    xhrRef.current?.abort();
    xhrRef.current = null;
    setProgress(0);
    setUploadKey(null);
    setError(null);
    setShortfall(null);

    try {
      const presign = await apiFetch<PresignResponse>("/api/uploads", {
        method: "POST",
        body: JSON.stringify({
          filename: nextFile.name,
          size_bytes: nextFile.size,
          content_type: nextFile.type || "application/octet-stream",
        }),
      });
      if (id !== uploadId.current) return;

      const xhr = new XMLHttpRequest();
      xhrRef.current = xhr;
      await putFile(xhr, presign.upload_url, nextFile, (percent) => {
        if (id === uploadId.current) setProgress(percent);
      });
      if (id !== uploadId.current) return;

      setProgress(100);
      setUploadKey(presign.upload_key);
    } catch (err) {
      if (id !== uploadId.current) return;
      setProgress(null);
      setError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Upload failed. Try again.",
      );
    } finally {
      if (id === uploadId.current) xhrRef.current = null;
    }
  }

  async function selectFile(nextFile: File) {
    const id = ++selectionId.current;
    const validation = validateUploadFile(nextFile);
    if (validation) {
      setFileError(validation);
      return;
    }

    setFileError(null);
    setError(null);
    setShortfall(null);
    setFile(nextFile);
    setDuration(null);
    setUploadKey(null);
    setProgress(null);

    const detected = await readAudioDuration(nextFile);
    if (id !== selectionId.current) return;
    setDuration(detected);
    void beginUpload(nextFile);
  }

  function clearFile() {
    selectionId.current += 1;
    uploadId.current += 1;
    xhrRef.current?.abort();
    xhrRef.current = null;
    setFile(null);
    setDuration(null);
    setProgress(null);
    setUploadKey(null);
    setFileError(null);
    setError(null);
    setShortfall(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !uploadKey) return;

    const validation = validatePipeline(config);
    if (validation) {
      setError(validation);
      return;
    }

    setSubmitting(true);
    setError(null);
    setShortfall(null);
    try {
      const job = await apiFetch<Job>("/api/jobs", {
        method: "POST",
        body: JSON.stringify({
          upload_key: uploadKey,
          source_filename: file.name,
          fps,
          pipeline: config,
        }),
      });
      queryClient.invalidateQueries({ queryKey: ["profile"] });
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        const payload = err.payload as {
          required_minutes?: unknown;
          available_minutes?: unknown;
        } | null;
        const required =
          typeof payload?.required_minutes === "number"
            ? payload.required_minutes
            : estimateCredits(duration);
        const available =
          typeof payload?.available_minutes === "number"
            ? payload.available_minutes
            : (profileQuery.data?.profile.credit_balance_minutes ?? 0);
        setShortfall({ required, available });
      } else if (err instanceof ApiError || err instanceof Error) {
        setError(err.message);
      } else {
        setError("Could not create the job. Try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const uploadInProgress = progress !== null && progress < 100;
  const pipelineError = validatePipeline(config);
  const canSubmit = Boolean(
    file && uploadKey && !submitting && !uploadInProgress && !pipelineError,
  );
  const balance = profileQuery.data?.profile.credit_balance_minutes ?? 0;
  const estimated = estimateCredits(duration);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
            New job
          </h1>
          <p className="mt-2 max-w-[58ch] text-[15px] leading-6 text-on-surface-variant">
            Upload a recording, choose the stages, and prepare clean audio, a
            speaker-attributed transcript, and a frame-accurate cut plan.
          </p>
        </div>
        <Link
          to="/"
          className="text-sm text-on-surface-variant underline decoration-outline underline-offset-4 transition-colors duration-150 ease-standard hover:text-on-surface hover:decoration-on-surface"
        >
          Back to dashboard
        </Link>
      </div>

      <form
        onSubmit={submit}
        className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)] lg:items-start"
      >
        <div className="space-y-6">
          <Panel
            title="Source media"
            description="Audio or video from the shoot. The original file is never modified."
          >
            <Dropzone
              file={file}
              duration={duration}
              progress={progress}
              disabled={submitting}
              error={fileError}
              onSelect={(next) => void selectFile(next)}
              onClear={clearFile}
            />
          </Panel>

          <Panel
            title="Pipeline"
            description="Run the whole chain or only the stages you need."
          >
            <PipelineToggles
              config={config}
              onChange={setConfig}
              disabled={submitting}
            />
          </Panel>
        </div>

        <aside className="space-y-6 lg:sticky lg:top-8">
          <Panel
            title="Timeline delivery"
            description="Timecodes and frame ranges use this rate."
          >
            <label
              htmlFor="fps"
              className="mb-2 block text-[13px] font-medium text-on-surface-variant"
            >
              Frame rate
            </label>
            <select
              id="fps"
              value={fps}
              disabled={submitting}
              onChange={(event) => setFps(event.target.value)}
              className={fieldClass}
            >
              {FPS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option} fps
                </option>
              ))}
            </select>
            <p className="mt-3 text-[13px] leading-5 text-on-surface-variant">
              Timecodes in the transcript and ROUGH-CUT.md snap to this rate.
            </p>
          </Panel>

          <Panel title="Estimate">
            <dl className="space-y-3 text-[13px]">
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-on-surface-variant">Source duration</dt>
                <dd className="font-mono text-on-surface">
                  {file
                    ? duration === null
                      ? "Server reads it"
                      : formatDuration(duration)
                    : "—"}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-on-surface-variant">Estimated reserve</dt>
                <dd className="font-mono text-on-surface">{estimated} min</dd>
              </div>
              <div className="flex items-baseline justify-between gap-4 border-t border-outline-variant pt-3">
                <dt className="text-on-surface-variant">Available</dt>
                <dd className="font-mono text-on-surface">
                  {balance.toFixed(1)} min
                </dd>
              </div>
            </dl>

            <p className="mt-4 text-[12px] leading-5 text-on-surface-variant">
              The reserve is charged when the job starts and refunded if it
              fails. Each started minute is billed as a whole minute.
            </p>

            {shortfall ? (
              <div className="mt-5 rounded-lg border border-error/25 bg-error-container p-4">
                <p className="text-sm text-on-error-container">
                  Insufficient credits: need {shortfall.required}, have{" "}
                  {shortfall.available}.
                </p>
                <p className="mt-2 text-[13px] leading-5 text-on-error-container/80">
                  Top-ups are not available in this build. Your upload is saved,
                  so you can retry after adding credits.
                </p>
                <button
                  type="button"
                  disabled
                  className="mt-3 h-9 rounded-[18px] border border-error/30 px-4 text-[13px] text-on-error-container/60"
                >
                  Top up (coming soon)
                </button>
              </div>
            ) : null}

            {error ? (
              <div
                role="alert"
                className="mt-5 rounded-lg border border-error/25 bg-error-container p-4 text-sm text-on-error-container"
              >
                <p>{error}</p>
                {file && !uploadKey && !uploadInProgress ? (
                  <button
                    type="button"
                    onClick={() => void beginUpload(file)}
                    className="mt-3 h-9 rounded-[18px] border border-error/30 px-4 text-[13px]"
                  >
                    Retry upload
                  </button>
                ) : null}
              </div>
            ) : null}

            {pipelineError ? (
              <p className="mt-4 text-[12px] leading-5 text-on-surface-variant">
                {pipelineError}
              </p>
            ) : null}

            <button
              type="submit"
              disabled={!canSubmit}
              className="mt-5 h-11 w-full rounded-[20px] bg-primary px-5 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting
                ? "Creating job…"
                : uploadInProgress
                  ? "Uploading…"
                  : "Create job"}
            </button>
          </Panel>
        </aside>
      </form>
    </div>
  );
}
