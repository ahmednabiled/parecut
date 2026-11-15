import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, apiFetch } from "../api/client";
import type { Job, PresignResponse, ProfileResponse } from "../api/types";
import Dropzone from "../components/Dropzone";
import Panel from "../components/Panel";
import { readAudioDuration, validateUploadFile } from "../lib/audio";

const FPS_OPTIONS = ["24", "25", "29.97", "30", "60"];

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

export default function NewJob() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const profileQuery = useQuery<ProfileResponse>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileResponse>("/api/profile"),
  });

  const [file, setFile] = useState<File | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [fps, setFps] = useState("25");
  const [progress, setProgress] = useState<number | null>(null);
  const [uploadKey, setUploadKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const hydrated = useRef(false);
  const selectionId = useRef(0);
  const uploadId = useRef(0);
  const xhrRef = useRef<XMLHttpRequest | null>(null);

  useEffect(() => {
    const data = profileQuery.data;
    if (!data || hydrated.current) return;
    hydrated.current = true;
    setFps(data.profile.default_fps);
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
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !uploadKey) return;

    setSubmitting(true);
    setError(null);
    try {
      const job = await apiFetch<Job>("/api/jobs", {
        method: "POST",
        body: JSON.stringify({
          upload_key: uploadKey,
          source_filename: file.name,
          fps,
          draft: true,
        }),
      });
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setError(
          "Insufficient credits for this upload. Top up, then try again.",
        );
      } else if (err instanceof ApiError || err instanceof Error) {
        setError(err.message);
      } else {
        setError("Could not create the project. Try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const uploadInProgress = progress !== null && progress < 100;
  const canSubmit = Boolean(
    file && uploadKey && !submitting && !uploadInProgress,
  );
  const balance = profileQuery.data?.profile.credit_balance_minutes ?? 0;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
            New project
          </h1>
          <p className="mt-2 max-w-[58ch] text-[15px] leading-6 text-on-surface-variant">
            Upload a recording to open the editor. The original stays untouched;
            apply effects, listen to the layers, and export captions from the
            timeline.
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
        <Panel
          title="Source media"
          description="Audio or video from the shoot. Creating a project costs no credits."
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
              className="h-12 w-full rounded border border-outline bg-surface-container-low px-4 text-[15px] text-on-surface transition-[border-color,background-color] duration-150 ease-standard hover:border-on-surface-variant focus:border-on-surface"
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

          <Panel title="Project">
            <dl className="space-y-3 text-[13px]">
              <div className="flex items-baseline justify-between gap-4">
                <dt className="text-on-surface-variant">Credits used now</dt>
                <dd className="font-mono text-on-surface">0 min</dd>
              </div>
              <div className="flex items-baseline justify-between gap-4 border-t border-outline-variant pt-3">
                <dt className="text-on-surface-variant">Available</dt>
                <dd className="font-mono text-on-surface">
                  {balance.toFixed(1)} min
                </dd>
              </div>
            </dl>

            <p className="mt-4 text-[12px] leading-5 text-on-surface-variant">
              Effects reserve minutes when they start and refund them if they
              fail. You choose each effect in the editor.
            </p>

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

            <button
              type="submit"
              disabled={!canSubmit}
              className="mt-5 h-11 w-full rounded-[20px] bg-primary px-5 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting
                ? "Creating project…"
                : uploadInProgress
                  ? "Uploading…"
                  : "Open editor"}
            </button>
          </Panel>
        </aside>
      </form>
    </div>
  );
}
