import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiFetch } from "../api/client";
import type { ProfileResponse } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
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
  const { me } = useAuth();
  const profileQuery = useQuery<ProfileResponse>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileResponse>("/api/profile"),
  });

  const jobs = profileQuery.data?.jobs ?? [];
  const balance =
    profileQuery.data?.profile.credit_balance_minutes ??
    me?.profile.credit_balance_minutes ??
    0;
  const deliverables = jobs.reduce((total, job) => total + job.artifacts.length, 0);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
            Dashboard
          </h1>
          <p className="mt-2 max-w-[52ch] text-[15px] leading-6 text-on-surface-variant">
            Recent audio jobs and the deliverables they produced.
          </p>
        </div>
        <Link
          to="/new"
          className="inline-flex h-10 items-center rounded-[20px] bg-primary px-5 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9]"
        >
          New job
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
            <div className="flex items-baseline justify-between py-4">
              <dt className="text-[13px] text-on-surface-variant">Jobs</dt>
              <dd className="font-mono text-lg text-on-surface">
                {profileQuery.isPending ? "..." : jobs.length}
              </dd>
            </div>
            <div className="flex items-baseline justify-between py-4">
              <dt className="text-[13px] text-on-surface-variant">Deliverables</dt>
              <dd className="font-mono text-lg text-on-surface">
                {profileQuery.isPending ? "..." : deliverables}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-[22px] font-medium leading-7 tracking-[-0.01em]">
          Recent jobs
        </h2>

        {profileQuery.isPending ? (
          <p className="mt-4 flex items-center gap-2 text-[13px] text-on-surface-variant">
            <span className="spinner" aria-hidden="true" />
            Loading jobs
          </p>
        ) : profileQuery.isError ? (
          <p className="mt-4 rounded-lg border border-error/25 bg-error-container px-4 py-3 text-sm text-on-error-container">
            Could not load your jobs. Refresh to try again.
          </p>
        ) : jobs.length === 0 ? (
          <div className="mt-4 rounded-xl border border-outline-variant bg-surface-container-low px-6 py-10">
            <h3 className="text-[15px] font-medium text-on-surface">No jobs yet</h3>
            <p className="mt-2 max-w-[52ch] text-[14px] leading-6 text-on-surface-variant">
              Upload a recording to create clean stems, a speaker-attributed
              transcript, and a rough-cut specification.
            </p>
            <Link
              to="/new"
              className="mt-5 inline-flex h-10 items-center rounded-[20px] border border-outline px-5 text-sm font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high"
            >
              Create a job
            </Link>
          </div>
        ) : (
          <div className="mt-4 overflow-hidden rounded-xl border border-outline-variant bg-surface-container">
            {jobs.map((job, index) => (
              <Link
                key={job.id}
                to={`/jobs/${job.id}`}
                className="grid grid-cols-[2rem_1fr_auto] items-center gap-4 border-b border-outline-variant px-4 py-4 transition-colors duration-150 ease-standard last:border-b-0 hover:bg-surface-container-high"
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
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
