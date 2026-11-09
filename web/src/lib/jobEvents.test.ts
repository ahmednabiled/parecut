import { describe, expect, it } from "vitest";
import type { Job } from "../api/types";
import { applyJobEvent } from "./jobEvents";

const base = {
  id: "j1",
  status: "running",
  stage_states: {
    transcribe: {
      status: "pending",
      percent: 0,
      started_at: null,
      completed_at: null,
    },
  },
  speaker_roles: {},
  artifacts: [],
} as unknown as Job;

describe("applyJobEvent", () => {
  it("updates a stage's percent", () => {
    const next = applyJobEvent(base, {
      type: "stage.progress",
      job_id: "j1",
      stage: "transcribe",
      percent: 75,
    });

    expect(next.stage_states.transcribe.percent).toBe(75);
    expect(next.stage_states.transcribe.status).toBe("running");
  });

  it("marks a stage completed at 100 percent", () => {
    const next = applyJobEvent(base, {
      type: "stage.completed",
      job_id: "j1",
      stage: "transcribe",
      percent: 100,
    });

    expect(next.stage_states.transcribe.status).toBe("completed");
    expect(next.stage_states.transcribe.percent).toBe(100);
    expect(next.stage_states.transcribe.completed_at).not.toBeNull();
  });

  it("marks the job completed and ignores unrelated events", () => {
    const done = applyJobEvent(base, {
      type: "job.completed",
      job_id: "j1",
    });

    expect(done.status).toBe("completed");
    expect(done.completed_at).not.toBeNull();
    expect(applyJobEvent(base, { type: "ping", job_id: "j1" } as never)).toBe(base);
  });

  it("records the failure code", () => {
    const failed = applyJobEvent(base, {
      type: "job.failed",
      job_id: "j1",
      message: "runpod_failed",
    });

    expect(failed.status).toBe("failed");
    expect(failed.error_code).toBe("runpod_failed");
  });

  it("replaces the job from a snapshot", () => {
    const snapshot = { ...base, status: "queued" } as Job;

    expect(applyJobEvent(base, { type: "snapshot", job: snapshot })).toBe(snapshot);
  });
});
