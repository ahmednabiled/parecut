import type { JobStatus } from "../api/types";

const STYLES: Record<JobStatus, string> = {
  queued: "border border-outline-variant text-on-surface-variant",
  running: "bg-surface-container-high text-on-surface",
  completed: "bg-primary text-on-primary",
  failed: "bg-error-container text-on-error-container",
};

const LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

export default function StatusPill({ status }: { status: JobStatus }) {
  return (
    <span
      className={`inline-flex h-6 items-center gap-2 rounded-lg px-2 text-[12px] font-medium ${STYLES[status]}`}
    >
      {status === "running" ? <span className="spinner" aria-hidden="true" /> : null}
      {LABELS[status]}
    </span>
  );
}
