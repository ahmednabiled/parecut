import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, apiFetch } from "../api/client";
import type { Job } from "../api/types";
import ArtifactTabs from "../components/ArtifactTabs";
import Panel from "../components/Panel";
import SpeakerRoles from "../components/SpeakerRoles";
import StageTimeline from "../components/StageTimeline";
import StatusPill from "../components/StatusPill";
import { useJobEvents } from "../hooks/useJobEvents";
import { formatDuration } from "../lib/format";
import { applyJobEvent, type LiveJobEvent } from "../lib/jobEvents";

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-on-surface-variant">{label}</dt>
      <dd className="text-right font-mono text-on-surface">{value}</dd>
    </div>
  );
}

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const jobQuery = useQuery<Job>({
    queryKey: ["job", id],
    queryFn: () => apiFetch<Job>(`/api/jobs/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && (data.status === "queued" || data.status === "running")
        ? 3000
        : false;
    },
  });

  const job = jobQuery.data;
  const terminal = job?.status === "completed" || job?.status === "failed";

  const handleEvent = useCallback(
    (event: LiveJobEvent) => {
      if (!id) return;

      if (event.type === "snapshot" && "job" in event) {
        queryClient.setQueryData(["job", id], event.job);
        return;
      }

      queryClient.setQueryData<Job>(["job", id], (current) =>
        current ? applyJobEvent(current, event) : current,
      );

      if (event.type === "job.completed" || event.type === "job.failed") {
        void queryClient.invalidateQueries({ queryKey: ["job", id] });
        void queryClient.invalidateQueries({ queryKey: ["profile"] });
      }
    },
    [id, queryClient],
  );

  useJobEvents(id, Boolean(job && !terminal), handleEvent);

  if (!id) {
    return (
      <div>
        <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
          Job not found
        </h1>
        <Link
          to="/"
          className="mt-4 inline-block text-sm text-on-surface-variant underline decoration-outline underline-offset-4 hover:text-on-surface"
        >
          Back to dashboard
        </Link>
      </div>
    );
  }

  if (jobQuery.isError) {
    return (
      <div>
        <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
          Job detail
        </h1>
        <p
          role="alert"
          className="mt-6 max-w-xl rounded-lg border border-error/25 bg-error-container px-4 py-3 text-sm text-on-error-container"
        >
          {jobQuery.error instanceof ApiError
            ? jobQuery.error.message
            : "Could not load this job."}
        </p>
        <Link
          to="/"
          className="mt-4 inline-block text-sm text-on-surface-variant underline decoration-outline underline-offset-4 hover:text-on-surface"
        >
          Back to dashboard
        </Link>
      </div>
    );
  }

  if (jobQuery.isPending || !job) {
    return (
      <div>
        <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
          Job detail
        </h1>
        <p className="mt-4 flex items-center gap-2 text-[13px] text-on-surface-variant">
          <span className="spinner" aria-hidden="true" />
          Loading job
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="truncate text-[32px] font-semibold leading-10 tracking-[-0.02em]">
              {job.source_filename}
            </h1>
            <StatusPill status={job.status} />
          </div>
          <p className="mt-2 font-mono text-[13px] text-on-surface-variant">
            {formatDuration(job.duration_seconds)} · {job.fps} fps
            {job.sample_rate ? ` · ${job.sample_rate} Hz` : ""}
            {" · "}
            {job.artifacts.length} files
            {" · "}
            Created {formatDate(job.created_at)}
          </p>
        </div>

        <Link
          to="/"
          className="text-sm text-on-surface-variant underline decoration-outline underline-offset-4 transition-colors duration-150 ease-standard hover:text-on-surface hover:decoration-on-surface"
        >
          Back to dashboard
        </Link>
      </div>

      {job.status === "failed" ? (
        <div
          role="alert"
          className="mt-6 rounded-xl border border-error/25 bg-error-container p-4 text-sm text-on-error-container"
        >
          <p className="font-medium">
            This job failed{job.error_code ? ` (${job.error_code})` : ""}.
          </p>
          <p className="mt-1 text-on-error-container/80">
            Reserved credits were refunded. You can create a new job with the
            same source.
          </p>
        </div>
      ) : null}

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)] lg:items-start">
        <div className="space-y-6">
          <Panel
            title="Progress"
            description="Stages update live. A reload rebuilds the timeline from the saved job state."
          >
            <StageTimeline job={job} />
          </Panel>

          <Panel
            title="Deliverables"
            description="Preview and download everything this job produced."
          >
            <ArtifactTabs job={job} />
          </Panel>
        </div>

        <aside className="space-y-6 lg:sticky lg:top-8">
          <Panel
            title="Speaker roles"
            description="Change who is on camera and regenerate the cut outputs instantly."
          >
            <SpeakerRoles job={job} />
          </Panel>

          <Panel title="Job details">
            <dl className="space-y-3 text-[13px]">
              <DetailRow label="Created" value={formatDate(job.created_at)} />
              <DetailRow label="Started" value={formatDate(job.started_at)} />
              <DetailRow
                label="Completed"
                value={formatDate(job.completed_at)}
              />
              <div className="border-t border-outline-variant pt-3">
                <DetailRow
                  label="Duration"
                  value={formatDuration(job.duration_seconds)}
                />
              </div>
              <DetailRow label="Frame rate" value={`${job.fps} fps`} />
              <DetailRow
                label="Sample rate"
                value={job.sample_rate ? `${job.sample_rate} Hz` : "Unknown"}
              />
              <DetailRow
                label="Deliverables"
                value={`${job.artifacts.length} files`}
              />
              {job.error_code ? (
                <DetailRow label="Error" value={job.error_code} />
              ) : null}
            </dl>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
