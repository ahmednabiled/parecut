import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api/client";
import type { JobStatus, ProfileResponse } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import Icon from "../components/Icon";
import StatusPill from "../components/StatusPill";
import { formatDuration } from "../lib/format";

type StatusFilter = "all" | JobStatus;

const STATUS_LABELS: Record<StatusFilter, string> = {
  all: "All",
  completed: "Completed",
  running: "Running",
  queued: "Queued",
  failed: "Failed",
};

function formatDate(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Dashboard() {
  const { me } = useAuth();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const profileQuery = useQuery<ProfileResponse>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileResponse>("/api/profile"),
  });

  const jobs = profileQuery.data?.jobs ?? [];
  const balance =
    profileQuery.data?.profile.credit_balance_minutes ??
    me?.profile.credit_balance_minutes ??
    0;
  const defaultFps =
    profileQuery.data?.profile.default_fps ??
    me?.profile.default_fps ??
    "25";
  const deliverables = jobs.reduce((total, job) => total + job.artifacts.length, 0);

  const statusCounts = useMemo(() => {
    const counts: Record<StatusFilter, number> = {
      all: jobs.length,
      completed: 0,
      running: 0,
      queued: 0,
      failed: 0,
    };
    for (const job of jobs) {
      counts[job.status] += 1;
    }
    return counts;
  }, [jobs]);

  const filteredJobs = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return jobs.filter((job) => {
      if (statusFilter !== "all" && job.status !== statusFilter) return false;
      if (needle && !job.source_filename.toLowerCase().includes(needle)) {
        return false;
      }
      return true;
    });
  }, [jobs, query, statusFilter]);

  const availableStatuses = (
    ["all", "completed", "running", "queued", "failed"] as const
  ).filter((status) => status === "all" || statusCounts[status] > 0);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
            Dashboard
          </h1>
          <p className="mt-2 max-w-[52ch] text-[15px] leading-6 text-on-surface-variant">
            Recent audio projects and the deliverables they produced.
          </p>
        </div>
        <Link
          to="/new"
          className="inline-flex h-10 items-center gap-2 rounded-[20px] bg-primary px-5 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9]"
        >
          <Icon name="add" size={16} />
          New project
        </Link>
      </div>

      <section className="mt-8 overflow-hidden rounded-xl border border-outline-variant bg-surface-container">
        <div className="grid lg:grid-cols-[1.45fr_1fr]">
          <div className="p-6">
            <p className="text-[13px] text-on-surface-variant">Processing credits</p>
            <p className="mt-2 font-mono text-[40px] font-medium leading-none tracking-[-0.03em]">
              {balance.toFixed(1)}
              <span className="ml-2 font-sans text-sm font-normal tracking-normal text-on-surface-variant">
                minutes
              </span>
            </p>
            <p className="mt-4 max-w-[46ch] text-[13px] leading-5 text-on-surface-variant">
              Charges are reserved when a job starts and refunded if it fails.
            </p>
          </div>

          <dl className="flex flex-col justify-center divide-y divide-outline-variant border-t border-outline-variant px-6 py-2 lg:border-l lg:border-t-0">
            <div className="flex items-baseline justify-between py-3.5">
              <dt className="text-[13px] text-on-surface-variant">Projects</dt>
              <dd className="font-mono text-lg text-on-surface">
                {profileQuery.isPending ? "…" : jobs.length}
              </dd>
            </div>
            <div className="flex items-baseline justify-between py-3.5">
              <dt className="text-[13px] text-on-surface-variant">Deliverables</dt>
              <dd className="font-mono text-lg text-on-surface">
                {profileQuery.isPending ? "…" : deliverables}
              </dd>
            </div>
            <div className="flex items-baseline justify-between py-3.5">
              <dt className="text-[13px] text-on-surface-variant">Default rate</dt>
              <dd className="font-mono text-sm text-on-surface">
                <Link
                  to="/settings"
                  className="underline decoration-outline-variant underline-offset-4 transition-colors duration-150 ease-standard hover:decoration-on-surface"
                >
                  {defaultFps} fps
                </Link>
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="mt-10">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-[22px] font-medium leading-7 tracking-[-0.01em]">
            Recent projects
          </h2>

          {jobs.length > 0 ? (
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative">
                <Icon
                  name="search"
                  size={16}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
                />
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Filter by filename…"
                  aria-label="Filter projects by filename"
                  className="h-9 w-56 rounded-full border border-outline-variant bg-surface-container-low pl-9 pr-8 text-[13px] text-on-surface placeholder:text-on-surface-variant/70 transition-colors duration-150 ease-standard hover:border-outline focus:border-on-surface"
                />
                {query ? (
                  <button
                    type="button"
                    onClick={() => setQuery("")}
                    aria-label="Clear search"
                    className="absolute right-2 top-1/2 grid size-5 -translate-y-1/2 place-items-center rounded-full text-on-surface-variant hover:text-on-surface"
                  >
                    <Icon name="close" size={14} />
                  </button>
                ) : null}
              </div>

              {availableStatuses.length > 2 ? (
                <div
                  role="group"
                  aria-label="Filter by status"
                  className="flex flex-wrap items-center gap-1"
                >
                  {availableStatuses.map((status) => (
                    <button
                      key={status}
                      type="button"
                      onClick={() => setStatusFilter(status)}
                      aria-pressed={statusFilter === status}
                      className={`inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[12px] font-medium transition-colors duration-150 ease-standard ${
                        statusFilter === status
                          ? "bg-primary text-on-primary"
                          : "border border-outline-variant text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
                      }`}
                    >
                      {STATUS_LABELS[status]}
                      <span className="font-mono text-[11px] opacity-75">
                        {statusCounts[status]}
                      </span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        {profileQuery.isPending ? (
          <div
            aria-label="Loading projects"
            className="mt-4 divide-y divide-outline-variant overflow-hidden rounded-xl border border-outline-variant bg-surface-container"
          >
            {[0, 1, 2].map((row) => (
              <div
                key={row}
                className="grid grid-cols-[2rem_1fr_auto] items-center gap-4 px-4 py-4"
              >
                <span className="h-3 w-5 rounded bg-surface-container-high" />
                <div className="space-y-2">
                  <span className="block h-3.5 w-48 rounded bg-surface-container-high" />
                  <span className="block h-3 w-64 rounded bg-surface-container-low" />
                </div>
                <span className="h-6 w-20 rounded-lg bg-surface-container-high" />
              </div>
            ))}
          </div>
        ) : profileQuery.isError ? (
          <p className="mt-4 rounded-lg border border-error/25 bg-error-container px-4 py-3 text-sm text-on-error-container">
            Could not load your projects. Refresh to try again.
          </p>
        ) : jobs.length === 0 ? (
          <div className="mt-4 rounded-xl border border-outline-variant bg-surface-container-low px-6 py-10">
            <h3 className="text-[15px] font-medium text-on-surface">No projects yet</h3>
            <p className="mt-2 max-w-[52ch] text-[14px] leading-6 text-on-surface-variant">
              Upload a recording to create clean stems, a speaker-attributed
              transcript, and a rough-cut specification.
            </p>
            <Link
              to="/new"
              className="mt-5 inline-flex h-10 items-center rounded-[20px] border border-outline px-5 text-sm font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high"
            >
              Create a project
            </Link>
          </div>
        ) : filteredJobs.length === 0 ? (
          <div className="mt-4 rounded-xl border border-outline-variant bg-surface-container-low px-6 py-8">
            <p className="text-[14px] text-on-surface">
              No projects match your current filter.
            </p>
            <button
              type="button"
              onClick={() => {
                setQuery("");
                setStatusFilter("all");
              }}
              className="mt-4 inline-flex h-9 items-center rounded-[18px] border border-outline px-4 text-[13px] font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high"
            >
              Clear filters
            </button>
          </div>
        ) : (
          <div className="mt-4 overflow-hidden rounded-xl border border-outline-variant bg-surface-container">
            {filteredJobs.map((job, index) => (
              <Link
                key={job.id}
                to={`/jobs/${job.id}`}
                className="group grid grid-cols-[2rem_1fr_auto_auto] items-center gap-4 border-b border-outline-variant px-4 py-4 transition-colors duration-150 ease-standard last:border-b-0 hover:bg-surface-container-high"
              >
                <span className="font-mono text-[12px] text-on-surface-variant">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-on-surface">
                    {job.source_filename}
                  </p>
                  <p className="mt-1 truncate font-mono text-[12px] text-on-surface-variant">
                    {job.fps} fps · {formatDuration(job.duration_seconds)} ·{" "}
                    {job.artifacts.length} files
                    <span className="hidden sm:inline"> · {formatDate(job.created_at)}</span>
                  </p>
                </div>
                <StatusPill status={job.status} />
                <Icon
                  name="arrow_forward"
                  size={16}
                  className="text-on-surface-variant transition-transform duration-150 ease-standard group-hover:translate-x-0.5 group-hover:text-on-surface"
                />
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
