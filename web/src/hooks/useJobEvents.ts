import { useEffect, useRef } from "react";
import type { Job, JobEvent } from "../api/types";
import type { LiveJobEvent } from "../lib/jobEvents";

const EVENT_TYPES = [
  "job.status",
  "stage.started",
  "stage.progress",
  "stage.completed",
  "job.completed",
  "job.failed",
] as const;

export function useJobEvents(
  jobId: string | undefined,
  enabled: boolean,
  onEvent: (event: LiveJobEvent) => void,
): void {
  const callbackRef = useRef(onEvent);

  useEffect(() => {
    callbackRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!jobId || !enabled || typeof EventSource === "undefined") return;

    const source = new EventSource(`/api/jobs/${jobId}/events`);
    const handle = (type: string) => (raw: Event) => {
      const message = raw as MessageEvent<string>;
      try {
        const data: unknown = JSON.parse(message.data);
        if (type === "snapshot") {
          callbackRef.current({ type: "snapshot", job: data as Job });
        } else {
          callbackRef.current(data as JobEvent);
        }
      } catch {
        // A malformed event is ignored; the next poll recovers the snapshot.
      }
    };

    source.addEventListener("snapshot", handle("snapshot"));
    for (const type of EVENT_TYPES) {
      source.addEventListener(type, handle(type));
    }

    return () => source.close();
  }, [jobId, enabled]);
}
