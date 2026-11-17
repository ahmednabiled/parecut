import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, apiFetch } from "../api/client";
import type {
  ArabicDialect,
  Artifact,
  AudioFormat,
  EffectName,
  Job,
  StudioChain,
  TranscriptionLanguage,
} from "../api/types";
import Inspector from "../components/editor/Inspector";
import Timeline from "../components/editor/Timeline";
import type { EditorTrack } from "../components/editor/types";
import Viewer from "../components/editor/Viewer";
import Icon from "../components/Icon";
import StatusPill from "../components/StatusPill";
import { useTimelineAudio } from "../hooks/useTimelineAudio";
import {
  captionCueKey,
  chunkCaptions,
  cuesToSrt,
  parseTranscript,
  type CaptionCue,
} from "../lib/captions";
import {
  AUDIO_KINDS,
  DEFAULT_ARABIC_DIALECT,
  DEFAULT_AUDIO_FORMAT,
  DEFAULT_LANGUAGES,
  DEFAULT_STUDIO,
  effectLabel,
  RUNNING_STATUSES,
} from "../lib/effects";
import { formatDuration } from "../lib/format";

interface Shortfall {
  required: number;
  available: number;
}

interface TranscriptSource {
  job: Job;
  artifact: Artifact;
}

type TranscriptVariant = "before" | "after";

const EMPTY_EFFECTS: Job[] = [];

function findArtifact(
  job: Job | null,
  kind: string,
  format: string,
): Artifact | null {
  return (
    job?.artifacts.find(
      (artifact) => artifact.kind === kind && artifact.format === format,
    ) ?? null
  );
}

function locateTranscript(
  project: Job | null,
  effects: Job[],
  selectedTrackId: string,
  variant: TranscriptVariant,
): TranscriptSource | null {
  if (!project) return null;
  const sourceId = selectedTrackId === "original" ? null : selectedTrackId;
  const kind = variant === "after" ? "transcript_after" : "transcript_before";
  const fallbackKind =
    variant === "after" ? "transcript_before" : "transcript_after";

  for (let index = effects.length - 1; index >= 0; index -= 1) {
    const run = effects[index];
    if (run.effect !== "transcribe" || run.status !== "completed") continue;
    if ((run.source_artifact_id ?? null) !== sourceId) continue;
    const artifact =
      findArtifact(run, kind, "json") ?? findArtifact(run, fallbackKind, "json");
    if (artifact) return { job: run, artifact };
  }

  if (sourceId !== null) return null;

  const artifact =
    findArtifact(project, kind, "json") ??
    findArtifact(project, fallbackKind, "json");
  return artifact ? { job: project, artifact } : null;
}

function locateSpeakerJob(
  project: Job | null,
  effects: Job[],
  selectedTrackId: string,
): Job | null {
  if (!project) return null;
  const sourceId = selectedTrackId === "original" ? null : selectedTrackId;

  for (let index = effects.length - 1; index >= 0; index -= 1) {
    const run = effects[index];
    if (run.effect !== "transcribe" || run.status !== "completed") continue;
    if ((run.source_artifact_id ?? null) !== sourceId) continue;
    if (Object.keys(run.speaker_roles ?? {}).length > 0) {
      return run;
    }
  }

  if (sourceId !== null) return null;
  return Object.keys(project.speaker_roles ?? {}).length > 0 ? project : null;
}

function buildTracks(project: Job | null, effects: Job[]): EditorTrack[] {
  if (!project) return [];

  const tracks: EditorTrack[] = [
    {
      id: "original",
      label: "Original audio",
      src: project.source_url,
      peaksSrc: project.source_peaks_url,
      kind: "original",
      group: "Source",
    },
  ];

  for (const artifact of project.artifacts) {
    if (!AUDIO_KINDS.has(artifact.kind)) continue;
    tracks.push({
      id: artifact.id,
      label: artifact.label,
      src: artifact.content_url,
      peaksSrc: artifact.peaks_url,
      kind: "audio",
      group: "Project files",
      artifact,
    });
  }

  for (const run of effects) {
    if (run.status !== "completed") continue;
    for (const artifact of run.artifacts) {
      if (!AUDIO_KINDS.has(artifact.kind)) continue;
      tracks.push({
        id: artifact.id,
        label: artifact.label,
        src: artifact.content_url,
        peaksSrc: artifact.peaks_url,
        kind: "audio",
        group: effectLabel(run.effect),
        artifact,
      });
    }
  }

  return tracks;
}

function numberOr(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export default function JobEditor() {
  const { id } = useParams();
  const queryClient = useQueryClient();

  const [chunkWords, setChunkWords] = useState(5);
  const [transcriptVariant, setTranscriptVariant] =
    useState<TranscriptVariant>("before");
  const [muted, setMuted] = useState<Record<string, boolean>>({});
  const [selectedTrackId, setSelectedTrackId] = useState("original");
  const [deletingTrackId, setDeletingTrackId] = useState<string | null>(null);
  const [captionEdits, setCaptionEdits] = useState<Record<string, string>>({});
  const [applyError, setApplyError] = useState<string | null>(null);
  const [shortfall, setShortfall] = useState<Shortfall | null>(null);

  const projectQuery = useQuery<Job>({
    queryKey: ["job", id],
    queryFn: () => apiFetch<Job>(`/api/jobs/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data && RUNNING_STATUSES.has(query.state.data.status)
        ? 2500
        : false,
  });

  const effectsQuery = useQuery<Job[]>({
    queryKey: ["job-effects", id],
    queryFn: () => apiFetch<Job[]>(`/api/jobs/${id}/effects`),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data?.some((run) => RUNNING_STATUSES.has(run.status))
        ? 2500
        : false,
  });

  const project = projectQuery.data ?? null;
  const effects = effectsQuery.data ?? EMPTY_EFFECTS;

  const tracks = useMemo(() => buildTracks(project, effects), [project, effects]);
  const selectedTrack = useMemo(
    () =>
      tracks.find((track) => track.id === selectedTrackId) ??
      tracks[0] ??
      null,
    [tracks, selectedTrackId],
  );
  const activeTrackId = selectedTrack?.id ?? "original";
  const transcriptSource = useMemo(
    () => locateTranscript(project, effects, activeTrackId, transcriptVariant),
    [project, effects, activeTrackId, transcriptVariant],
  );
  const speakerJob = useMemo(
    () => locateSpeakerJob(project, effects, activeTrackId),
    [project, effects, activeTrackId],
  );
  const transcriptArtifact = transcriptSource?.artifact ?? null;

  const transcriptQuery = useQuery<string>({
    queryKey: ["transcript", transcriptArtifact?.id],
    queryFn: async () => {
      if (!transcriptArtifact) throw new Error("No transcript");
      const response = await fetch(transcriptArtifact.content_url, {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error("Could not load the transcript.");
      }
      return response.text();
    },
    enabled: Boolean(transcriptArtifact),
    staleTime: Infinity,
  });

  const segments = useMemo(
    () => parseTranscript(transcriptQuery.data ?? ""),
    [transcriptQuery.data],
  );
  const cues = useMemo(
    () => chunkCaptions(segments, chunkWords),
    [segments, chunkWords],
  );
  const editedCues = useMemo(
    () =>
      cues.map((cue) => {
        const edit = captionEdits[captionCueKey(cue)];
        return edit ? { ...cue, text: edit } : cue;
      }),
    [cues, captionEdits],
  );

  const storageKey = transcriptArtifact
    ? `parecut-captions:${id}:${transcriptArtifact.id}`
    : null;

  useEffect(() => {
    if (!storageKey) {
      setCaptionEdits({});
      return;
    }
    try {
      const raw = window.localStorage.getItem(storageKey);
      setCaptionEdits(
        raw ? (JSON.parse(raw) as Record<string, string>) : {},
      );
    } catch {
      setCaptionEdits({});
    }
  }, [storageKey]);

  const duration = project?.duration_seconds ?? 0;
  const mutedTracks = useMemo(
    () =>
      Object.fromEntries(
        tracks.map((track) => [
          track.id,
          muted[track.id] ?? track.kind !== "original",
        ]),
      ) as Record<string, boolean>,
    [tracks, muted],
  );
  const playbackTracks = useMemo(
    () =>
      tracks.filter(
        (track) => track.kind === "original" || !mutedTracks[track.id],
      ),
    [tracks, mutedTracks],
  );
  const audio = useTimelineAudio(
    playbackTracks,
    mutedTracks,
    duration > 0 ? duration : 3600,
  );

  const applyMutation = useMutation({
    mutationFn: (variables: {
      effect: EffectName;
      enhanceMix?: number;
      studio?: StudioChain;
      languages?: TranscriptionLanguage[];
      audioFormat?: AudioFormat;
      arabicDialect?: ArabicDialect;
      sourceArtifactId?: string;
    }) => {
      const payload: Record<string, unknown> = { effect: variables.effect };
      if (variables.enhanceMix !== undefined) {
        payload.enhance_mix = variables.enhanceMix;
      }
      if (variables.studio !== undefined) {
        payload.studio = variables.studio;
      }
      if (variables.languages !== undefined) {
        payload.languages = variables.languages;
      }
      if (variables.arabicDialect !== undefined) {
        payload.arabic_dialect = variables.arabicDialect;
      }
      if (variables.audioFormat !== undefined) {
        payload.audio_format = variables.audioFormat;
      }
      if (variables.sourceArtifactId !== undefined) {
        payload.source_artifact_id = variables.sourceArtifactId;
      }
      return apiFetch<Job>(`/api/jobs/${id}/effects`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: (run) => {
      queryClient.setQueryData<Job[]>(["job-effects", id], (current) => [
        ...(current ?? []),
        run,
      ]);
      void queryClient.invalidateQueries({ queryKey: ["job-effects", id] });
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
      setApplyError(null);
      setShortfall(null);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 402) {
        const payload = error.payload as {
          required_minutes?: unknown;
          available_minutes?: unknown;
        } | null;
        setShortfall({
          required: numberOr(payload?.required_minutes, 1),
          available: numberOr(payload?.available_minutes, 0),
        });
        setApplyError(null);
        return;
      }
      setShortfall(null);
      setApplyError(
        error instanceof Error
          ? error.message
          : "Could not apply the effect. Try again.",
      );
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (artifactId: string) =>
      apiFetch<void>(`/api/jobs/${id}/artifacts/${artifactId}`, {
        method: "DELETE",
      }),
    onMutate: (artifactId) => {
      setDeletingTrackId(artifactId);
      setApplyError(null);
    },
    onSuccess: () => {
      setDeletingTrackId(null);
      void queryClient.invalidateQueries({ queryKey: ["job", id] });
      void queryClient.invalidateQueries({ queryKey: ["job-effects", id] });
    },
    onError: (error) => {
      setDeletingTrackId(null);
      setApplyError(
        error instanceof Error
          ? error.message
          : "Could not delete the track. Try again.",
      );
    },
  });

  const handleDeleteTrack = useCallback(
    (trackId: string) => {
      deleteMutation.mutate(trackId);
    },
    [deleteMutation],
  );

  const handleApply = useCallback(
    (
      effect: EffectName,
      enhanceMix?: number,
      studio?: StudioChain,
      languages?: TranscriptionLanguage[],
      audioFormat?: AudioFormat,
      arabicDialect?: ArabicDialect,
    ) => {
      setApplyError(null);
      setShortfall(null);
      const sourceArtifactId =
        selectedTrack && selectedTrack.kind !== "original"
          ? selectedTrack.id
          : undefined;
      applyMutation.mutate({
        effect,
        enhanceMix,
        studio,
        languages,
        audioFormat,
        arabicDialect,
        sourceArtifactId,
      });
    },
    [applyMutation, selectedTrack],
  );

  const handleToggleMute = useCallback(
    (trackId: string) => {
      const track = tracks.find((item) => item.id === trackId);
      setMuted((current) => {
        const isMuted =
          current[trackId] ?? (track ? track.kind !== "original" : true);
        return { ...current, [trackId]: !isMuted };
      });
    },
    [tracks],
  );

  const handleEditCue = useCallback(
    (cue: CaptionCue, text: string) => {
      setCaptionEdits((current) => {
        const key = captionCueKey(cue);
        const next = { ...current };
        if (text === cue.text) delete next[key];
        else next[key] = text;
        if (storageKey) {
          try {
            window.localStorage.setItem(storageKey, JSON.stringify(next));
          } catch {
            // Editing still works for this session without storage.
          }
        }
        return next;
      });
    },
    [storageKey],
  );

  const handleSpeakerUpdated = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["job-effects", id] });
    void queryClient.invalidateQueries({ queryKey: ["transcript"] });
  }, [queryClient, id]);

  function downloadCaptions() {
    if (!project || editedCues.length === 0) return;
    const srt = cuesToSrt(editedCues);
    const blob = new Blob([srt], {
      type: "application/x-subrip",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const base = project.source_filename.replace(/\.[^.]+$/, "");
    anchor.href = url;
    anchor.download = `${base || "captions"}.srt`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (!id) {
    return (
      <div>
        <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
          Project not found
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

  if (projectQuery.isError) {
    return (
      <div>
        <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
          Project
        </h1>
        <p
          role="alert"
          className="mt-6 max-w-xl rounded-lg border border-error/25 bg-error-container px-4 py-3 text-sm text-on-error-container"
        >
          {projectQuery.error instanceof ApiError
            ? projectQuery.error.message
            : "Could not load this project."}
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

  if (projectQuery.isPending || !project) {
    return (
      <div>
        <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
          Project
        </h1>
        <p className="mt-4 flex items-center gap-2 text-[13px] text-on-surface-variant">
          <span className="spinner" aria-hidden="true" />
          Loading project
        </p>
      </div>
    );
  }

  const processing = effects
    .filter((run) => RUNNING_STATUSES.has(run.status))
    .map((run) => ({
      id: run.id,
      effect: run.effect ?? "transcribe",
      label: run.effect ? effectLabel(run.effect) : "effect",
    }));

  return (
    <div className="flex flex-col xl:h-full xl:min-h-0 xl:flex-1">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-outline-variant pb-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="truncate text-[18px] font-semibold leading-6 tracking-[-0.01em]">
            {project.source_filename}
          </h1>
          <StatusPill status={project.status} />
          <p className="font-mono text-[11px] text-on-surface-variant">
            {formatDuration(project.duration_seconds)} · {project.fps} fps
            {project.sample_rate ? ` · ${project.sample_rate} Hz` : ""}
            {" · "}
            {tracks.length} track{tracks.length === 1 ? "" : "s"}
            {" · "}
            {effects.length} effect run{effects.length === 1 ? "" : "s"}
          </p>
        </div>

        <Link
          to="/"
          aria-label="Back to dashboard"
          className="grid size-8 shrink-0 place-items-center rounded-full text-on-surface-variant transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface"
        >
          <Icon name="arrow_back" size={16} />
        </Link>
      </div>

      {project.status === "failed" ? (
        <div
          role="alert"
          className="mt-4 shrink-0 rounded-xl border border-error/25 bg-error-container p-4 text-sm text-on-error-container"
        >
          <p className="font-medium">
            This project failed{project.error_code ? ` (${project.error_code})` : ""}.
          </p>
          <p className="mt-1 text-on-error-container/80">
            Reserved credits were refunded. The source file is still available
            in the timeline.
          </p>
        </div>
      ) : null}

      <div className="mt-4 grid min-h-0 min-w-0 gap-6 xl:flex-1 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,23rem)] xl:overflow-hidden">
        <div className="flex min-h-0 min-w-0 flex-col gap-6 xl:grid xl:min-h-0 xl:grid-rows-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <Viewer
            cues={editedCues}
            currentTime={audio.currentTime}
            chunkWords={chunkWords}
            onChunkWords={setChunkWords}
            onSeek={audio.seek}
            onEditCue={handleEditCue}
            onDownload={downloadCaptions}
            loading={Boolean(transcriptSource) && transcriptQuery.isPending}
            error={transcriptQuery.isError}
            hasTranscript={Boolean(transcriptSource)}
            variant={transcriptVariant}
            onVariant={setTranscriptVariant}
          />
          <Timeline
            tracks={tracks}
            muted={mutedTracks}
            onToggleMute={handleToggleMute}
            selectedTrackId={activeTrackId}
            onSelectTrack={setSelectedTrackId}
            onDeleteTrack={handleDeleteTrack}
            deletingTrackId={deletingTrackId}
            duration={duration}
            currentTime={audio.currentTime}
            getCurrentTime={audio.getCurrentTime}
            onSeek={audio.seek}
            isPlaying={audio.isPlaying}
            onTogglePlay={audio.toggle}
            levels={audio.levels}
            processing={processing}
          />
        </div>

        <Inspector
          effects={effects}
          applying={
            applyMutation.isPending
              ? (applyMutation.variables?.effect ?? null)
              : null
          }
          onApply={handleApply}
          inputLabel={selectedTrack?.label ?? "Original audio"}
          error={applyError}
          shortfall={shortfall}
          transcriptJob={transcriptSource?.job ?? null}
          speakerJob={speakerJob}
          onSpeakerUpdated={handleSpeakerUpdated}
          defaultMix={project.pipeline_config.enhance_mix}
          defaultStudio={
            project.pipeline_config.studio_chain ?? DEFAULT_STUDIO
          }
          defaultLanguages={
            project.pipeline_config.transcription_languages ??
            DEFAULT_LANGUAGES
          }
          defaultAudioFormat={
            project.pipeline_config.audio_format ?? DEFAULT_AUDIO_FORMAT
          }
          defaultDialect={
            project.pipeline_config.arabic_dialect ?? DEFAULT_ARABIC_DIALECT
          }
        />
      </div>

      <div className="hidden">
        {playbackTracks.map((track) => (
          <audio
            key={track.id}
            ref={audio.registerTrack(track.id)}
            src={track.src}
            preload="metadata"
          />
        ))}
      </div>
    </div>
  );
}
