import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, apiFetch } from "../api/client";
import type { Job, SpeakerRole } from "../api/types";

const ROLE_OPTIONS: { value: SpeakerRole; label: string }[] = [
  { value: "presenter", label: "Presenter" },
  { value: "feeder", label: "Feeder / Director" },
  { value: "cohost", label: "Co-host" },
];

const fieldClass =
  "h-11 w-full min-w-0 rounded border border-outline bg-transparent px-3 text-sm text-on-surface transition-[border-color,background-color] duration-150 ease-standard hover:border-on-surface-variant focus:border-on-surface disabled:cursor-not-allowed disabled:opacity-50";

export default function SpeakerRoles({
  job,
  onUpdated,
}: {
  job: Job;
  onUpdated?: (job: Job) => void;
}) {
  const queryClient = useQueryClient();
  const speakers = Object.keys(job.speaker_roles).sort();
  const locked = job.status === "queued" || job.status === "running";

  const [draft, setDraft] = useState<Record<string, SpeakerRole> | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const roles = draft ?? job.speaker_roles;

  const mutation = useMutation({
    mutationFn: (next: Record<string, SpeakerRole>) =>
      apiFetch<Job>(`/api/jobs/${job.id}/speakers`, {
        method: "PATCH",
        body: JSON.stringify({ roles: next }),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["job", job.id], updated);
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
      setDraft(null);
      setNotice("Speaker roles saved. Cut outputs regenerated.");
      setError(null);
      onUpdated?.(updated);
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not save speaker roles. Try again.",
      );
      setNotice(null);
    },
  });

  if (speakers.length === 0) {
    return (
      <p className="text-[13px] leading-5 text-on-surface-variant">
        Speaker roles appear after transcription finishes.
      </p>
    );
  }

  const changed = speakers.some(
    (speaker) => roles[speaker] !== job.speaker_roles[speaker],
  );

  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2">
        {speakers.map((speaker) => (
          <div key={speaker} className="min-w-0">
            <label
              htmlFor={`speaker-${speaker}`}
              className="mb-2 block font-mono text-[12px] text-on-surface-variant"
            >
              {speaker}
            </label>
            <select
              id={`speaker-${speaker}`}
              value={roles[speaker] ?? "presenter"}
              disabled={locked || mutation.isPending}
              onChange={(event) => {
                setDraft({
                  ...roles,
                  [speaker]: event.target.value as SpeakerRole,
                });
                setNotice(null);
                setError(null);
              }}
              className={fieldClass}
            >
              {ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>

      <p className="mt-4 text-[12px] leading-5 text-on-surface-variant">
        Presenter and co-host lines are kept. Feeder lines are treated as
        off-camera prompts and removed.
      </p>

      {locked ? (
        <p className="mt-2 text-[12px] leading-5 text-on-surface-variant">
          Roles can be changed when the job finishes.
        </p>
      ) : null}

      <button
        type="button"
        disabled={!changed || locked || mutation.isPending}
        onClick={() => mutation.mutate(roles)}
        className="mt-4 h-10 rounded-[20px] bg-primary px-5 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {mutation.isPending ? "Regenerating…" : "Save roles"}
      </button>

      {notice ? (
        <p className="mt-4 rounded-lg bg-surface-container-high px-4 py-3 text-[13px] text-on-surface">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-error/25 bg-error-container px-4 py-3 text-[13px] text-on-error-container"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
