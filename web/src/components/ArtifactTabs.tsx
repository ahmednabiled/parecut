import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Artifact, Job } from "../api/types";
import { formatFileSize } from "../lib/format";

type TabKey = "audio" | "before" | "after" | "roughcut";

const AUDIO_KINDS = new Set([
  "cleaned_audio",
  "enhanced_audio",
  "stem_music",
  "stem_dialogue",
  "stem_speaker",
]);

const TABS: { key: TabKey; label: string; empty: string }[] = [
  {
    key: "audio",
    label: "Audio",
    empty:
      "No audio artifacts yet. Enable noise reduction, enhancement, or separation to produce audio.",
  },
  {
    key: "before",
    label: "Transcript (Before)",
    empty:
      "The before-cut transcript appears after transcription finishes.",
  },
  {
    key: "after",
    label: "Transcript (After)",
    empty:
      "The after-cut transcript appears when the rough-cut stage finishes.",
  },
  {
    key: "roughcut",
    label: "ROUGH-CUT.md",
    empty:
      "ROUGH-CUT.md appears when the rough-cut stage finishes.",
  },
];

function groupArtifacts(job: Job): Record<TabKey, Artifact[]> {
  return {
    audio: job.artifacts.filter((artifact) => AUDIO_KINDS.has(artifact.kind)),
    before: job.artifacts.filter(
      (artifact) => artifact.kind === "transcript_before",
    ),
    after: job.artifacts.filter(
      (artifact) => artifact.kind === "transcript_after",
    ),
    roughcut: job.artifacts.filter(
      (artifact) => artifact.kind === "rough_cut_md",
    ),
  };
}

function ArtifactCard({ artifact }: { artifact: Artifact }) {
  const isAudio = artifact.format === "wav";
  const isMarkdown = artifact.format === "md";
  const copyable = artifact.kind === "rough_cut_md";
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">(
    "idle",
  );

  const textQuery = useQuery({
    queryKey: ["artifact-text", artifact.id],
    queryFn: async () => {
      const response = await fetch(artifact.download_url, {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`Could not load ${artifact.label}.`);
      }
      return response.text();
    },
    enabled: !isAudio,
    staleTime: Infinity,
  });

  async function copy() {
    if (!textQuery.data) return;
    if (!navigator.clipboard) {
      setCopyState("error");
      return;
    }
    try {
      await navigator.clipboard.writeText(textQuery.data);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      setCopyState("error");
    }
  }

  return (
    <article className="rounded-lg border border-outline-variant bg-surface-container-low p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-on-surface">{artifact.label}</p>
          <p className="mt-1 font-mono text-[11px] text-on-surface-variant">
            {artifact.format.toUpperCase()} · {formatFileSize(artifact.size_bytes)}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {copyable ? (
            <button
              type="button"
              onClick={() => void copy()}
              disabled={!textQuery.data}
              className="inline-flex h-8 items-center rounded-[16px] border border-outline px-3 text-[12px] font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-50"
            >
              {copyState === "copied"
                ? "Copied"
                : copyState === "error"
                  ? "Copy failed"
                  : "Copy for coding agent"}
            </button>
          ) : null}
          <a
            href={artifact.download_url}
            download
            className="inline-flex h-8 items-center rounded-[16px] border border-outline px-3 text-[12px] font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high"
          >
            Download
          </a>
        </div>
      </div>

      {isAudio ? (
        <audio
          controls
          preload="metadata"
          src={artifact.download_url}
          className="mt-4 w-full"
        />
      ) : textQuery.isPending ? (
        <p className="mt-4 flex items-center gap-2 text-[13px] text-on-surface-variant">
          <span className="spinner" aria-hidden="true" />
          Loading preview
        </p>
      ) : textQuery.isError ? (
        <p className="mt-4 text-[13px] text-on-surface-variant">
          Preview unavailable. Download the file to inspect it.
        </p>
      ) : isMarkdown ? (
        <div className="markdown mt-4 max-h-[40rem] overflow-auto rounded-lg border border-outline-variant bg-surface-container-lowest p-5">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {textQuery.data ?? ""}
          </ReactMarkdown>
        </div>
      ) : (
        <pre className="mt-4 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-outline-variant bg-surface-container-lowest p-4 font-mono text-[12px] leading-5 text-on-surface">
          {textQuery.data}
        </pre>
      )}

      {copyState === "error" ? (
        <p className="mt-2 text-[12px] text-error">
          Could not copy. Select the text manually.
        </p>
      ) : null}
    </article>
  );
}

export default function ArtifactTabs({ job }: { job: Job }) {
  const [active, setActive] = useState<TabKey>("audio");
  const groups = groupArtifacts(job);
  const artifacts = groups[active];
  const activeTab = TABS.find((tab) => tab.key === active) ?? TABS[0];

  return (
    <div>
      <div
        role="tablist"
        aria-label="Job artifacts"
        className="flex flex-wrap gap-1 border-b border-outline-variant"
      >
        {TABS.map((tab) => {
          const selected = tab.key === active;
          const count = groups[tab.key].length;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              id={`artifact-tab-${tab.key}`}
              aria-selected={selected}
              aria-controls={`artifact-panel-${tab.key}`}
              onClick={() => setActive(tab.key)}
              className={`inline-flex h-10 items-center border-b-2 px-3 text-[13px] transition-colors duration-150 ease-standard ${
                selected
                  ? "border-primary text-on-surface"
                  : "border-transparent text-on-surface-variant hover:text-on-surface"
              }`}
            >
              {tab.label}
              <span className="ml-2 font-mono text-[11px] text-on-surface-variant">
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`artifact-panel-${active}`}
        aria-labelledby={`artifact-tab-${active}`}
        className="mt-4"
      >
        {artifacts.length === 0 ? (
          <div className="rounded-lg border border-dashed border-outline-variant bg-surface-container-low px-5 py-8">
            <p className="max-w-[52ch] text-[13px] leading-5 text-on-surface-variant">
              {activeTab.empty}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {artifacts.map((artifact) => (
              <ArtifactCard key={artifact.id} artifact={artifact} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
