export type SpeakerRole = "presenter" | "feeder" | "cohost";
export type JobStatus = "queued" | "running" | "completed" | "failed";
export type StageStatus = "pending" | "running" | "completed" | "skipped" | "failed";
export type JobEventType =
  | "snapshot"
  | "job.status"
  | "stage.started"
  | "stage.progress"
  | "stage.completed"
  | "job.completed"
  | "job.failed";

export interface UserRead {
  id: string;
  email: string;
  full_name: string;
  avatar_url: string | null;
  created_at: string;
}

export interface ProfileRead {
  credit_balance_minutes: number;
  default_fps: string;
  default_enhance_mix: number;
  default_silence_pad_ms: number;
}

export interface SessionUser {
  user: UserRead;
  profile: ProfileRead;
}

export interface StageState {
  status: StageStatus;
  percent: number;
  started_at: string | null;
  completed_at: string | null;
}

export interface PipelineConfig {
  noise_reduction: boolean;
  enhance: boolean;
  enhance_mix: number;
  studio_chain: StudioChain;
  separate_music: boolean;
  separate_speakers: boolean;
  transcribe: boolean;
  rough_cut: boolean;
  transcription_languages: TranscriptionLanguage[];
  arabic_dialect: ArabicDialect;
  audio_format: AudioFormat;
}

export interface StudioChain {
  enabled: boolean;
  highpass_hz: number;
  body_db: number;
  mud_db: number;
  presence_db: number;
  deesser: number;
  compressor_threshold_db: number;
  compressor_ratio: number;
  compressor_attack_ms: number;
  compressor_release_ms: number;
  limiter_db: number;
  loudness_lufs: number;
}

export interface Artifact {
  id: string;
  kind: string;
  label: string;
  format: string;
  size_bytes: number;
  download_url: string;
  content_url: string;
  peaks_url: string;
}

export type EffectName =
  | "noise_reduction"
  | "enhance"
  | "separate_music"
  | "separate_speakers"
  | "transcribe";

export type TranscriptionLanguage = "en" | "ar";
export type ArabicDialect =
  | "auto"
  | "msa"
  | "egyptian"
  | "gulf"
  | "levantine"
  | "maghrebi"
  | "iraqi";
export type AudioFormat = "mp3" | "wav";

export interface Job {
  id: string;
  parent_job_id: string | null;
  effect: EffectName | null;
  status: JobStatus;
  source_filename: string;
  source_url: string;
  source_peaks_url: string;
  duration_seconds: number | null;
  sample_rate: number | null;
  fps: string;
  pipeline_config: PipelineConfig;
  speaker_roles: Record<string, SpeakerRole>;
  stage_states: Record<string, StageState>;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  artifacts: Artifact[];
}

export interface LedgerEntry {
  id: string;
  job_id: string | null;
  delta_minutes: number;
  reason: string;
  created_at: string;
}

export interface ProfileResponse {
  user: UserRead;
  profile: ProfileRead;
  jobs: Job[];
  ledger: LedgerEntry[];
}

export interface JobEvent {
  type: JobEventType;
  job_id: string;
  stage?: string | null;
  percent?: number | null;
  message?: string | null;
  at?: string;
}

export interface PresignResponse {
  upload_url: string;
  upload_key: string;
  expires_at: string;
}
