import { CheckCircle2, CircleDashed, LoaderCircle, XCircle } from "lucide-react";
import type { JobStatus } from "../api/types";

const STYLES: Record<JobStatus, string> = {
  queued: "border-ink-500 bg-ink-800 text-mist-400",
  running: "border-signal-500/30 bg-signal-500/10 text-signal-400",
  completed: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
  failed: "border-red-500/25 bg-red-500/10 text-red-300",
};

const LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

const ICONS = {
  queued: CircleDashed,
  running: LoaderCircle,
  completed: CheckCircle2,
  failed: XCircle,
};

export default function StatusPill({ status }: { status: JobStatus }) {
  const Icon = ICONS[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] ${STYLES[status]}`}
    >
      <Icon size={12} className={status === "running" ? "animate-spin" : ""} />
      {LABELS[status]}
    </span>
  );
}
