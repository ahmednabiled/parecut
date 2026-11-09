import type { Job, StageState, StageStatus } from "../api/types";
import { STAGES, STAGE_STATUS_LABELS } from "../lib/stages";

const EMPTY_STATE: StageState = {
  status: "pending",
  percent: 0,
  started_at: null,
  completed_at: null,
};

function formatTimestamp(value: string | null): string {
  if (!value) return "";
  return new Date(value).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function dotClass(status: StageStatus): string {
  switch (status) {
    case "completed":
      return "bg-primary";
    case "running":
      return "bg-on-surface ring-2 ring-on-surface/25";
    case "failed":
      return "bg-error";
    case "skipped":
      return "bg-surface-container-highest";
    default:
      return "border border-outline-variant";
  }
}

function textClass(status: StageStatus): string {
  switch (status) {
    case "failed":
      return "text-error";
    case "pending":
    case "skipped":
      return "text-on-surface-variant";
    default:
      return "text-on-surface";
  }
}

export default function StageTimeline({ job }: { job: Job }) {
  return (
    <ol className="divide-y divide-outline-variant">
      {STAGES.map((stage) => {
        const state = job.stage_states[stage.key] ?? EMPTY_STATE;
        const status: StageStatus =
          state.status === "running" && job.status === "failed"
            ? "failed"
            : state.status;
        const percent = Math.max(0, Math.min(100, state.percent ?? 0));
        const started = formatTimestamp(state.started_at);
        const completed = formatTimestamp(state.completed_at);

        return (
          <li key={stage.key} className="flex gap-4 py-4 first:pt-0 last:pb-0">
            <span
              aria-hidden="true"
              className={`mt-1.5 size-2.5 shrink-0 rounded-full ${dotClass(status)}`}
            />

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm font-medium text-on-surface">{stage.label}</p>
                <span
                  className={`inline-flex items-center gap-2 text-[12px] ${textClass(status)}`}
                >
                  {status === "running" ? (
                    <span className="spinner" aria-hidden="true" />
                  ) : null}
                  {STAGE_STATUS_LABELS[status]}
                </span>
              </div>

              {status === "skipped" ? (
                <p className="mt-1 text-[12px] text-on-surface-variant">
                  Not selected for this job.
                </p>
              ) : (
                <>
                  <div
                    role="progressbar"
                    aria-label={`${stage.label} progress`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={percent}
                    className="mt-2 h-1 overflow-hidden rounded-full bg-surface-container-highest"
                  >
                    <div
                      className={`h-full origin-left transition-transform duration-200 ease-standard ${
                        status === "failed" ? "bg-error" : "bg-primary"
                      }`}
                      style={{ transform: `scaleX(${percent / 100})` }}
                    />
                  </div>
                  <p className="mt-1 font-mono text-[11px] text-on-surface-variant">
                    {started ? `Started ${started}` : "Not started"}
                    {completed ? ` · Done ${completed}` : ""}
                  </p>
                </>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
