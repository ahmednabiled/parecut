import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, AudioLines, FileAudio, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api/client";
import type { ProfileResponse } from "../api/types";
import StatusPill from "../components/StatusPill";
import { formatDuration } from "../lib/format";

function formatDate(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Dashboard() {
  const profileQuery = useQuery<ProfileResponse>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileResponse>("/api/profile"),
  });

  const jobs = profileQuery.data?.jobs ?? [];
  const balance = profileQuery.data?.profile.credit_balance_minutes ?? 0;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal-500">
            Workspace
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em]">Dashboard</h1>
          <p className="mt-2 text-sm text-mist-400">
            Your recent audio jobs and the deliverables they produced.
          </p>
        </div>
        <Link
          to="/new"
          className="inline-flex items-center gap-2 rounded-lg bg-signal-500 px-4 py-2.5 text-sm font-semibold text-ink-950 transition hover:bg-signal-400"
        >
          <Plus size={16} />
          New job
        </Link>
      </div>

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <section className="rounded-xl border border-ink-700 bg-ink-850 p-5">
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-mist-400">
            <AudioLines size={13} className="text-signal-500" />
            Processing credits
          </div>
          <p className="mt-3 text-3xl font-semibold tracking-tight">
            {balance.toFixed(1)}
            <span className="ml-1 text-sm font-normal text-mist-400">minutes</span>
          </p>
          <p className="mt-2 text-xs text-mist-500">
            Charges are reserved when a job starts and refunded if it fails.
          </p>
        </section>

        <section className="rounded-xl border border-ink-700 bg-ink-850 p-5">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-mist-400">
            Jobs
          </div>
          <p className="mt-3 text-3xl font-semibold tracking-tight">{jobs.length}</p>
          <p className="mt-2 text-xs text-mist-500">Most recent ten jobs are shown.</p>
        </section>

        <section className="rounded-xl border border-ink-700 bg-ink-850 p-5">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-mist-400">
            Deliverables
          </div>
          <p className="mt-3 text-3xl font-semibold tracking-tight">
            {jobs.reduce((total, job) => total + job.artifacts.length, 0)}
          </p>
          <p className="mt-2 text-xs text-mist-500">
            Stems, transcripts, and rough-cut specs available.
          </p>
        </section>
      </div>

      <section className="mt-10">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-mist-200">Recent jobs</h2>
          {profileQuery.isFetching ? (
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-mist-500">
              Syncing…
            </span>
          ) : null}
        </div>

        {profileQuery.isPending ? (
          <div className="mt-4 space-y-2">
            {[0, 1, 2].map((row) => (
              <div key={row} className="h-[72px] animate-pulse rounded-xl bg-ink-850" />
            ))}
          </div>
        ) : profileQuery.isError ? (
          <p className="mt-4 rounded-xl border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            Could not load your jobs. Refresh to try again.
          </p>
        ) : jobs.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-ink-600 bg-ink-900/40 px-6 py-12 text-center">
            <FileAudio size={26} className="mx-auto text-mist-500" />
            <h3 className="mt-4 text-sm font-medium text-mist-200">No jobs yet</h3>
            <p className="mx-auto mt-2 max-w-sm text-sm text-mist-400">
              Upload a recording to create your first clean stems and rough-cut
              specification.
            </p>
            <Link
              to="/new"
              className="mt-5 inline-flex items-center gap-2 rounded-lg border border-ink-600 px-4 py-2 text-sm text-mist-200 transition hover:border-signal-500/50 hover:text-mist-100"
            >
              <Plus size={15} />
              Create a job
            </Link>
          </div>
        ) : (
          <div className="mt-4 overflow-hidden rounded-xl border border-ink-700">
            {jobs.map((job) => (
              <Link
                key={job.id}
                to={`/jobs/${job.id}`}
                className="group flex items-center gap-4 border-b border-ink-800 bg-ink-900/40 px-4 py-4 transition last:border-b-0 hover:bg-ink-850"
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-lg border border-ink-700 bg-ink-800 text-mist-400">
                  <FileAudio size={17} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-mist-100">
                    {job.source_filename}
                  </p>
                  <p className="mt-1 truncate font-mono text-[11px] text-mist-500">
                    {job.fps} fps · {formatDuration(job.duration_seconds)} ·{" "}
                    {job.artifacts.length} files · {formatDate(job.created_at)}
                  </p>
                </div>
                <StatusPill status={job.status} />
                <ArrowUpRight
                  size={16}
                  className="hidden text-mist-500 transition group-hover:text-signal-500 sm:block"
                />
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
