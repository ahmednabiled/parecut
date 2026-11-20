import type { Artifact, EffectName } from "../../api/types";

export interface EditorTrack {
  id: string;
  label: string;
  src: string;
  peaksSrc: string;
  kind: "original" | "audio";
  group: string;
  artifact?: Artifact;
}

export interface ProcessingRun {
  id: string;
  effect: EffectName;
  label: string;
  percent?: number | null;
}
