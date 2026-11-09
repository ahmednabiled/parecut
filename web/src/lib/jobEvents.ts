import type { Job, JobEvent, JobStatus, StageState } from "../api/types";

export interface JobSnapshot {
  type: "snapshot";
  job: Job;
}

export type LiveJobEvent = JobEvent | JobSnapshot;

const JOB_STATUSES: JobStatus[] = ["queued", "running", "completed", "failed"];

function isJobStatus(value: unknown): value is JobStatus {
  return typeof value === "string" && JOB_STATUSES.includes(value as JobStatus);
}

function nowIso(): string {
  return new Date().toISOString();
}

export function applyJobEvent(job: Job, event: LiveJobEvent): Job {
  if (event.type === "snapshot" && "job" in event) {
    return event.job;
  }

  switch (event.type) {
    case "job.status": {
      if (!isJobStatus(event.message)) return job;
      return {
        ...job,
        status: event.message,
        started_at:
          event.message === "running" && job.started_at === null
            ? nowIso()
            : job.started_at,
      };
    }

    case "stage.started":
    case "stage.progress":
    case "stage.completed": {
      if (!event.stage) return job;
      const current: StageState = job.stage_states[event.stage] ?? {
        status: "pending",
        percent: 0,
        started_at: null,
        completed_at: null,
      };
      const completed = event.type === "stage.completed";
      const now = nowIso();

      return {
        ...job,
        stage_states: {
          ...job.stage_states,
          [event.stage]: {
            ...current,
            status: completed ? "completed" : "running",
            percent: completed ? 100 : (event.percent ?? current.percent),
            started_at: current.started_at ?? now,
            completed_at: completed ? now : current.completed_at,
          },
        },
      };
    }

    case "job.completed":
      return {
        ...job,
        status: "completed",
        completed_at: job.completed_at ?? nowIso(),
      };

    case "job.failed":
      return {
        ...job,
        status: "failed",
        error_code: event.message ?? job.error_code ?? "job_failed",
        completed_at: job.completed_at ?? nowIso(),
      };

    default:
      return job;
  }
}
