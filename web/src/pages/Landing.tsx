import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import Icon from "../components/Icon";

type FlowBranch = "all" | "restore" | "separate" | "cut";

const PIPELINE_STAGES = [
  {
    step: "01",
    name: "Noise reduction",
    engine: "DeepFilterNet3",
    detail:
      "Suppresses room tone, HVAC hum, and handling noise while preserving natural vocal transients.",
  },
  {
    step: "02",
    name: "Studio enhancement",
    engine: "Resemble Enhance + Studio chain",
    detail:
      "Restores 44.1 kHz bandwidth and body with wet/dry mix control, followed by configurable high-pass, EQ, de-esser, compressor, limiter, and loudness normalization.",
  },
  {
    step: "03",
    name: "Stem & speaker separation",
    engine: "Demucs htdemucs_ft",
    detail:
      "Separates dialogue from music beds and exports per-speaker gated stems from diarization turns.",
  },
  {
    step: "04",
    name: "Mixed-language transcription",
    engine: "WhisperX large-v3-turbo + Nemotron-3",
    detail:
      "Produces word-level aligned transcripts and speaker attribution across English, Arabic, or multi-pass merged sessions.",
  },
  {
    step: "05",
    name: "Deterministic rough cut",
    engine: "ROUGH-CUT.md + SRT / VTT",
    detail:
      "Detects false starts and same-speaker retakes, filters off-camera feeders by role, and snaps keep/remove ranges to your project frame rate.",
  },
];

const DELIVERABLES = [
  {
    artifact: "enhanced.wav",
    spec: "44.1 kHz WAV",
    description: "Restored, noise-reduced, and studio-finished dialogue master.",
  },
  {
    artifact: "dialogue.wav / music.wav",
    spec: "Separated stems",
    description: "Isolated speech and music tracks for independent NLE mixing.",
  },
  {
    artifact: "speaker_*.wav",
    spec: "Gated stems",
    description: "Per-speaker tracks derived from diarization speaker turns.",
  },
  {
    artifact: "ROUGH-CUT.md",
    spec: "Frame-snapped spec",
    description:
      "Structured keep and remove timecode ranges for DaVinci Resolve or Premiere.",
  },
  {
    artifact: "captions.srt / raw.vtt",
    spec: "Word-chunked captions",
    description:
      "Editable client-side caption cues exported directly from the viewer.",
  },
];

const FLOW_PATHS: {
  id: Exclude<FlowBranch, "all">;
  label: string;
  caption: string;
  inPath: string;
  outPath: string;
  midY: number;
  stageNum: string;
  stageTitle: string;
  stageSub: string;
  outTitle: string;
  outSub: string;
}[] = [
  {
    id: "restore",
    label: "Restore",
    caption:
      "DeepFilterNet3 and Resemble Enhance strip room noise and finish dialogue to -16 LUFS.",
    inPath: "M 190 170 C 275 170, 295 76, 380 76",
    outPath: "M 560 76 C 645 76, 665 76, 750 76",
    midY: 76,
    stageNum: "01",
    stageTitle: "Denoise & Enhance",
    stageSub: "DeepFilterNet3 · Resemble",
    outTitle: "enhanced.wav",
    outSub: "44.1 kHz studio master",
  },
  {
    id: "separate",
    label: "Separate",
    caption:
      "Demucs htdemucs_ft isolates dialogue from music and exports gated per-speaker stems.",
    inPath: "M 190 170 L 380 170",
    outPath: "M 560 170 L 750 170",
    midY: 170,
    stageNum: "02",
    stageTitle: "Stem Separation",
    stageSub: "Demucs · Speaker gates",
    outTitle: "dialogue & music",
    outSub: "Isolated multi-track stems",
  },
  {
    id: "cut",
    label: "Transcribe & Cut",
    caption:
      "WhisperX and Nemotron-3 align English/Arabic speech and generate a frame-accurate ROUGH-CUT.md.",
    inPath: "M 190 170 C 275 170, 295 264, 380 264",
    outPath: "M 560 264 C 645 264, 665 264, 750 264",
    midY: 264,
    stageNum: "03",
    stageTitle: "Transcribe & Cut",
    stageSub: "WhisperX · Nemotron-3",
    outTitle: "ROUGH-CUT.md",
    outSub: "Keep / Remove + SRT",
  },
];

function SignalFlowMap() {
  const [activeBranch, setActiveBranch] = useState<FlowBranch>("all");

  const activeCaption =
    activeBranch === "all"
      ? "One source recording branches into parallel non-destructive stages and outputs NLE-ready deliverables."
      : FLOW_PATHS.find((p) => p.id === activeBranch)?.caption;

  return (
    <div
      aria-label="Signal flow map"
      className="mx-auto max-w-5xl overflow-hidden rounded-2xl border border-outline-variant bg-surface-container-lowest"
    >
      <div className="relative px-4 pb-2 pt-6 sm:px-8 sm:pt-8">
        <svg
          viewBox="0 0 940 340"
          className="h-auto w-full select-none text-on-surface"
          role="img"
          aria-label="Parecut signal flow from raw shoot audio through restoration, separation, and transcription to NLE deliverables"
        >
          {/* Subtle architectural blueprint rails */}
          <g stroke="currentColor" strokeOpacity={0.06} strokeWidth={1}>
            <line x1={105} y1={24} x2={105} y2={316} strokeDasharray="3 5" />
            <line x1={470} y1={24} x2={470} y2={316} strokeDasharray="3 5" />
            <line x1={835} y1={24} x2={835} y2={316} strokeDasharray="3 5" />
            <line x1={40} y1={170} x2={900} y2={170} strokeOpacity={0.03} />
          </g>

          {/* Column Labels */}
          <g
            fill="currentColor"
            fillOpacity={0.42}
            fontFamily="var(--font-mono)"
            fontSize={10}
          >
            <text x={105} y={22} textAnchor="middle">
              INPUT
            </text>
            <text x={470} y={22} textAnchor="middle">
              MODULAR PIPELINE
            </text>
            <text x={835} y={22} textAnchor="middle">
              NLE DELIVERABLES
            </text>
          </g>

          {/* Flow Curves & Animated Pulses */}
          {FLOW_PATHS.map((branch, idx) => {
            const isHighlighted =
              activeBranch === "all" || activeBranch === branch.id;
            const baseOpacity = isHighlighted ? 0.25 : 0.08;
            const pulseOpacity = isHighlighted ? 0.95 : 0.12;

            return (
              <g key={branch.id}>
                {/* Base static tracks */}
                <path
                  d={branch.inPath}
                  fill="none"
                  stroke="currentColor"
                  strokeOpacity={baseOpacity}
                  strokeWidth={1.5}
                />
                <path
                  d={branch.outPath}
                  fill="none"
                  stroke="currentColor"
                  strokeOpacity={baseOpacity}
                  strokeWidth={1.5}
                />

                {/* Animated signal pulses */}
                <path
                  d={branch.inPath}
                  fill="none"
                  stroke="currentColor"
                  strokeOpacity={pulseOpacity}
                  strokeWidth={2}
                  strokeLinecap="round"
                  className={
                    idx % 2 === 1
                      ? "animate-signal-flow-delayed"
                      : "animate-signal-flow"
                  }
                />
                <path
                  d={branch.outPath}
                  fill="none"
                  stroke="currentColor"
                  strokeOpacity={pulseOpacity}
                  strokeWidth={2}
                  strokeLinecap="round"
                  className={
                    idx % 2 === 0
                      ? "animate-signal-flow-delayed"
                      : "animate-signal-flow"
                  }
                />
              </g>
            );
          })}

          {/* Left Input Node: Raw Shoot Audio (Isometric stacked card) */}
          <g transform="translate(20, 126)">
            <rect
              x={6}
              y={6}
              width={170}
              height={88}
              rx={12}
              fill="#0a0a0a"
              stroke="currentColor"
              strokeOpacity={0.14}
            />
            <rect
              x={0}
              y={0}
              width={170}
              height={88}
              rx={12}
              fill="#141414"
              stroke="currentColor"
              strokeOpacity={0.35}
            />
            <text
              x={18}
              y={26}
              fill="currentColor"
              fillOpacity={0.5}
              fontFamily="var(--font-mono)"
              fontSize={10}
            >
              00 · SOURCE
            </text>
            <text
              x={18}
              y={46}
              fill="currentColor"
              fontSize={13}
              fontWeight={600}
            >
              Raw shoot audio
            </text>
            {/* Mini abstract waveform glyph */}
            <path
              d="M 18 66 Q 26 56, 34 66 T 50 66 T 66 62 T 82 66 T 98 58 T 114 66 T 130 66 T 148 66"
              fill="none"
              stroke="currentColor"
              strokeOpacity={0.65}
              strokeWidth={1.5}
              strokeLinecap="round"
            />
            <circle cx={170} cy={44} r={3.5} fill="currentColor" />
          </g>

          {/* Center Pipeline Nodes & Right Output Nodes */}
          {FLOW_PATHS.map((branch) => {
            const isHighlighted =
              activeBranch === "all" || activeBranch === branch.id;
            const nodeOpacity = isHighlighted ? 1 : 0.35;
            const yTop = branch.midY - 34;

            return (
              <g
                key={branch.id}
                style={{ opacity: nodeOpacity }}
                className="cursor-pointer transition-opacity duration-200"
                onClick={() =>
                  setActiveBranch((cur) =>
                    cur === branch.id ? "all" : branch.id,
                  )
                }
              >
                {/* Center Stage Node */}
                <g transform={`translate(380, ${yTop})`}>
                  <rect
                    x={4}
                    y={4}
                    width={180}
                    height={68}
                    rx={12}
                    fill="#0a0a0a"
                    stroke="currentColor"
                    strokeOpacity={0.12}
                  />
                  <rect
                    x={0}
                    y={0}
                    width={180}
                    height={68}
                    rx={12}
                    fill="#151515"
                    stroke="currentColor"
                    strokeOpacity={isHighlighted ? 0.45 : 0.2}
                  />
                  <circle cx={0} cy={34} r={3} fill="currentColor" />
                  <circle cx={180} cy={34} r={3} fill="currentColor" />
                  <text
                    x={16}
                    y={24}
                    fill="currentColor"
                    fillOpacity={0.5}
                    fontFamily="var(--font-mono)"
                    fontSize={10}
                  >
                    STAGE {branch.stageNum}
                  </text>
                  <text
                    x={16}
                    y={42}
                    fill="currentColor"
                    fontSize={13}
                    fontWeight={600}
                  >
                    {branch.stageTitle}
                  </text>
                  <text
                    x={16}
                    y={57}
                    fill="currentColor"
                    fillOpacity={0.55}
                    fontFamily="var(--font-mono)"
                    fontSize={10}
                  >
                    {branch.stageSub}
                  </text>
                </g>

                {/* Right Output Deliverable Node */}
                <g transform={`translate(750, ${yTop})`}>
                  <rect
                    x={0}
                    y={0}
                    width={170}
                    height={68}
                    rx={12}
                    fill="#101010"
                    stroke="currentColor"
                    strokeOpacity={isHighlighted ? 0.38 : 0.18}
                  />
                  <circle cx={0} cy={34} r={3} fill="currentColor" />
                  <text
                    x={16}
                    y={28}
                    fill="currentColor"
                    fontFamily="var(--font-mono)"
                    fontSize={12}
                    fontWeight={500}
                  >
                    {branch.outTitle}
                  </text>
                  <text
                    x={16}
                    y={48}
                    fill="currentColor"
                    fillOpacity={0.55}
                    fontSize={11}
                  >
                    {branch.outSub}
                  </text>
                </g>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Bottom Interactive Branch Selector + Caption */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-outline-variant bg-surface-container-low px-5 py-3.5">
        <div
          role="group"
          aria-label="Filter signal flow"
          className="flex flex-wrap items-center gap-1.5"
        >
          {(
            [
              ["all", "All flows"],
              ["restore", "01 Restore"],
              ["separate", "02 Separate"],
              ["cut", "03 Transcribe & Cut"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              aria-pressed={activeBranch === id}
              onClick={() => setActiveBranch(id)}
              className={`rounded-full px-3 py-1 text-[12px] font-medium transition-colors duration-150 ease-standard ${
                activeBranch === id
                  ? "bg-primary text-on-primary"
                  : "border border-outline-variant text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <p className="text-[12px] text-on-surface-variant">{activeCaption}</p>
      </div>
    </div>
  );
}

const STACK_ITEMS: Array<{ label: string; mono?: boolean }> = [
  { label: "WAV · MP4 · MOV", mono: true },
  { label: "Demucs" },
  { label: "WhisperX" },
  { label: "SRT · VTT", mono: true },
  { label: "DaVinci Resolve" },
  { label: "Premiere Pro" },
  { label: "ROUGH-CUT.md", mono: true },
];

export default function Landing() {
  const { me } = useAuth();

  return (
    <div className="min-h-screen bg-surface text-on-surface">
      <header className="sticky top-0 z-30">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 -bottom-6 top-0 bg-gradient-to-b from-surface via-surface/85 to-transparent backdrop-blur-md [mask-image:linear-gradient(to_bottom,black_55%,transparent_100%)]"
        />
        <div className="relative mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4 md:grid md:grid-cols-[1fr_auto_1fr]">
          <Link to="/" className="shrink-0 justify-self-start">
            <img
              src="/brand/login-logo.png"
              alt="Pare Cut"
              className="h-10 w-auto"
            />
          </Link>

          <nav
            aria-label="Landing navigation"
            className="hidden items-center gap-1 justify-self-center rounded-full border border-outline-variant bg-surface-container/85 px-2 py-1 text-[13px] text-on-surface-variant backdrop-blur-md md:flex"
          >
            <a
              href="#architecture"
              className="rounded-full px-3.5 py-1.5 transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface"
            >
              Architecture
            </a>
            <a
              href="#capabilities"
              className="rounded-full px-3.5 py-1.5 transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface"
            >
              Capabilities
            </a>
            <a
              href="#pipeline"
              className="rounded-full px-3.5 py-1.5 transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface"
            >
              Pipeline
            </a>
            <a
              href="#deliverables"
              className="rounded-full px-3.5 py-1.5 transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface"
            >
              Deliverables
            </a>
          </nav>

          <div className="flex items-center gap-2.5 justify-self-end">
            {me ? (
              <Link
                to="/"
                className="inline-flex h-9 items-center gap-2 rounded-[20px] bg-primary px-4 text-[13px] font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9]"
              >
                Open dashboard
                <Icon name="arrow_forward" size={15} />
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="inline-flex h-9 items-center rounded-[20px] px-3.5 text-[13px] font-medium text-on-surface-variant transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface"
                >
                  Sign in
                </Link>
                <Link
                  to="/register"
                  className="inline-flex h-9 items-center rounded-[20px] bg-primary px-4 text-[13px] font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9]"
                >
                  Get started
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        <section className="relative flex min-h-[calc(100svh-4.5rem)] flex-col justify-center overflow-hidden px-6 pt-16 pb-20 sm:pt-20 sm:pb-24">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 [background-image:radial-gradient(rgba(237,237,237,0.1)_1px,transparent_1px)] [background-size:24px_24px] [mask-image:radial-gradient(ellipse_65%_65%_at_50%_42%,black_25%,transparent_100%)]"
          />
          <div
            aria-hidden="true"
            className="animate-hero-mist pointer-events-none absolute -inset-x-12 bottom-0 h-80 [background-image:radial-gradient(ellipse_65%_55%_at_50%_65%,rgba(237,237,237,0.11),transparent_72%)]"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-b from-transparent to-surface"
          />

          <div className="relative mx-auto max-w-3xl text-center">
            <h1 className="text-[42px] font-semibold leading-[1.06] tracking-[-0.03em] sm:text-[60px]">
              Raw audio in.
              <br />
              <span className="font-light italic text-on-surface-variant">
                A clean cut out.
              </span>
            </h1>
            <p className="mx-auto mt-6 max-w-[54ch] text-[16px] leading-[26px] text-on-surface-variant">
              Turn raw shoot recordings into clean stems, a speaker-attributed
              transcript, and a frame-snapped{" "}
              <span className="font-mono text-[14px] text-on-surface">
                ROUGH-CUT.md
              </span>{" "}
              for Resolve or Premiere.
            </p>

            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              {me ? (
                <Link
                  to="/new"
                  className="inline-flex h-11 items-center gap-2 rounded-[20px] bg-primary px-6 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9]"
                >
                  New project
                  <Icon name="arrow_forward" size={16} />
                </Link>
              ) : (
                <Link
                  to="/register"
                  className="inline-flex h-11 items-center gap-2 rounded-[20px] bg-primary px-6 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9]"
                >
                  Start free
                  <span className="animate-arrow-nudge inline-flex">
                    <Icon name="arrow_forward" size={16} />
                  </span>
                </Link>
              )}
              <a
                href="#pipeline"
                className="inline-flex h-11 items-center rounded-[20px] border border-outline px-5 text-sm font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high"
              >
                Inspect pipeline
              </a>
            </div>
          </div>

          <div className="relative mx-auto mt-14 w-full max-w-3xl text-center">
            <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-on-surface-variant/80">
              Built for your post stack
            </p>
            <div className="mt-4 overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)]">
              <div className="animate-stack-marquee flex w-max items-center text-[13px] font-medium text-on-surface-variant">
                <div className="flex shrink-0 items-center gap-8 pr-8 whitespace-nowrap">
                  {STACK_ITEMS.map((item) => (
                    <span
                      key={item.label}
                      className={item.mono ? "font-mono text-[12px]" : undefined}
                    >
                      {item.label}
                    </span>
                  ))}
                </div>
                <div
                  aria-hidden="true"
                  className="flex shrink-0 items-center gap-8 pr-8 whitespace-nowrap"
                >
                  {STACK_ITEMS.map((item) => (
                    <span
                      key={`dup-${item.label}`}
                      className={item.mono ? "font-mono text-[12px]" : undefined}
                    >
                      {item.label}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section
          id="architecture"
          className="scroll-mt-20 border-b border-outline-variant px-6 py-20"
        >
          <div className="mx-auto max-w-5xl">
            <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="font-mono text-[12px] text-on-surface-variant">
                  Signal architecture
                </p>
                <h2 className="mt-2 text-[28px] font-semibold leading-9 tracking-[-0.02em]">
                  One recording, parallel non-destructive outputs.
                </h2>
              </div>
              <p className="font-mono text-[12px] text-on-surface-variant">
                Click any branch to isolate
              </p>
            </div>
            <SignalFlowMap />
          </div>
        </section>

        <section
          id="capabilities"
          className="scroll-mt-20 border-b border-outline-variant px-6 py-20"
        >
          <div className="mx-auto max-w-6xl">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div className="max-w-xl">
                <p className="font-mono text-[12px] text-on-surface-variant">
                  Built for real shoots
                </p>
                <h2 className="mt-3 text-[32px] font-semibold leading-10 tracking-[-0.02em]">
                  Everything needed between raw audio and the NLE timeline.
                </h2>
              </div>
              <p className="font-mono text-[12px] text-on-surface-variant">
                44.1 kHz · English & Arabic · 24–60 fps
              </p>
            </div>

            <div className="mt-10 grid gap-4 lg:grid-cols-12">
              <div className="rounded-2xl border border-outline-variant bg-surface-container p-7 lg:col-span-7">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-mono text-[12px] text-on-surface-variant">
                    01 · Restoration & stems
                  </p>
                  <span className="rounded-lg border border-outline-variant px-2 py-0.5 font-mono text-[11px] text-on-surface-variant">
                    44.1 kHz WAV
                  </span>
                </div>
                <h3 className="mt-4 text-[20px] font-medium tracking-[-0.01em]">
                  Strip room noise, isolate dialogue, and keep music separate.
                </h3>
                <p className="mt-3 max-w-[52ch] text-[14px] leading-6 text-on-surface-variant">
                  Run DeepFilterNet3, Resemble Enhance with a 7-stage studio
                  chain, and Demucs separation as independent non-destructive
                  tracks.
                </p>
                <div className="mt-5 flex flex-wrap gap-2 font-mono text-[11px] text-on-surface-variant">
                  <span className="rounded border border-outline-variant bg-surface-container-lowest px-2.5 py-1">
                    High-pass 80 Hz
                  </span>
                  <span className="rounded border border-outline-variant bg-surface-container-lowest px-2.5 py-1">
                    De-esser & Compressor
                  </span>
                  <span className="rounded border border-outline-variant bg-surface-container-lowest px-2.5 py-1">
                    -16 LUFS target
                  </span>
                </div>
              </div>

              <div className="rounded-2xl border border-outline-variant bg-surface-container-low p-7 lg:col-span-5">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-mono text-[12px] text-on-surface-variant">
                    02 · Cut preparation
                  </p>
                  <span className="rounded-lg border border-outline-variant px-2 py-0.5 font-mono text-[11px] text-on-surface-variant">
                    ROUGH-CUT.md
                  </span>
                </div>
                <h3 className="mt-4 text-[20px] font-medium tracking-[-0.01em]">
                  Deterministic false-start removal and speaker role filtering.
                </h3>
                <p className="mt-3 text-[14px] leading-6 text-on-surface-variant">
                  Toggle off-camera line feeders out and regenerate{" "}
                  <span className="font-mono text-[13px] text-on-surface">
                    ROUGH-CUT.md
                  </span>{" "}
                  instantly without re-running transcription.
                </p>
              </div>

              <div className="rounded-2xl border border-outline-variant bg-surface-container-low p-7 lg:col-span-5">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-mono text-[12px] text-on-surface-variant">
                    03 · Mixed-language ASR
                  </p>
                  <span className="rounded-lg border border-outline-variant px-2 py-0.5 font-mono text-[11px] text-on-surface-variant">
                    EN · AR
                  </span>
                </div>
                <h3 className="mt-4 text-[20px] font-medium tracking-[-0.01em]">
                  Word-level alignment and speaker attribution.
                </h3>
                <p className="mt-3 text-[14px] leading-6 text-on-surface-variant">
                  WhisperX large-v3-turbo and Nemotron-3-Diarization merge
                  English and Arabic passes by script and confidence.
                </p>
              </div>

              <div className="rounded-2xl border border-outline-variant bg-surface-container p-7 lg:col-span-7">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-mono text-[12px] text-on-surface-variant">
                    04 · Non-destructive timeline
                  </p>
                  <span className="rounded-lg border border-outline-variant px-2 py-0.5 font-mono text-[11px] text-on-surface-variant">
                    0 min draft
                  </span>
                </div>
                <h3 className="mt-4 text-[20px] font-medium tracking-[-0.01em]">
                  Audition every layer in sync before exporting.
                </h3>
                <p className="mt-3 max-w-[52ch] text-[14px] leading-6 text-on-surface-variant">
                  Projects open as free drafts. Apply effects on demand, mute
                  individual tracks in the Web Audio timeline, edit captions
                  inline, and export SRT or VTT directly.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section
          id="pipeline"
          className="scroll-mt-20 border-b border-outline-variant px-6 py-20"
        >
          <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[0.82fr_1.18fr]">
            <div className="lg:sticky lg:top-24 lg:self-start">
              <p className="font-mono text-[12px] text-on-surface-variant">
                01–05 · Modular stages
              </p>
              <h2 className="mt-3 text-[32px] font-semibold leading-10 tracking-[-0.02em]">
                One recording.
                <br />
                Five modular stages.
              </h2>
              <p className="mt-4 max-w-[46ch] text-[15px] leading-6 text-on-surface-variant">
                Every effect runs on demand as an isolated child job. The
                original recording stays untouched on the timeline while new
                stems and transcripts layer cleanly underneath.
              </p>
            </div>

            <ol className="divide-y divide-outline-variant overflow-hidden rounded-2xl border border-outline-variant bg-surface-container">
              {PIPELINE_STAGES.map((stage) => (
                <li
                  key={stage.step}
                  className="grid gap-3 px-6 py-5 sm:grid-cols-[2.5rem_1fr]"
                >
                  <span className="font-mono text-[13px] text-on-surface-variant">
                    {stage.step}
                  </span>
                  <div>
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <h3 className="text-[16px] font-medium text-on-surface">
                        {stage.name}
                      </h3>
                      <span className="font-mono text-[12px] text-on-surface-variant">
                        {stage.engine}
                      </span>
                    </div>
                    <p className="mt-2 max-w-[58ch] text-[14px] leading-6 text-on-surface-variant">
                      {stage.detail}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section
          id="deliverables"
          className="scroll-mt-20 border-b border-outline-variant px-6 py-20"
        >
          <div className="mx-auto grid max-w-6xl gap-8 lg:grid-cols-[1.15fr_0.85fr]">
            <div>
              <h2 className="text-[22px] font-medium leading-7 tracking-[-0.01em]">
                Deliverables built for the NLE
              </h2>
              <p className="mt-2 max-w-[54ch] text-[15px] leading-6 text-on-surface-variant">
                Download clean audio stems, frame-accurate cut specifications,
                and edited caption files straight from the project inspector.
              </p>

              <div className="mt-6 overflow-hidden rounded-2xl border border-outline-variant bg-surface-container">
                <div className="divide-y divide-outline-variant">
                  {DELIVERABLES.map((item) => (
                    <div
                      key={item.artifact}
                      className="grid gap-2 px-5 py-4 sm:grid-cols-[13rem_1fr] sm:items-baseline"
                    >
                      <div>
                        <p className="font-mono text-[13px] font-medium text-on-surface">
                          {item.artifact}
                        </p>
                        <p className="mt-0.5 font-mono text-[11px] text-on-surface-variant">
                          {item.spec}
                        </p>
                      </div>
                      <p className="text-[14px] leading-5 text-on-surface-variant">
                        {item.description}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div
              id="workflow"
              className="flex flex-col justify-between rounded-2xl border border-outline-variant bg-surface-container-low p-6"
            >
              <div>
                <h2 className="text-[22px] font-medium leading-7 tracking-[-0.01em]">
                  Non-destructive by design
                </h2>
                <p className="mt-2 text-[14px] leading-6 text-on-surface-variant">
                  Projects open as zero-cost drafts. You only spend processing
                  minutes on the effects you run.
                </p>

                <ol className="mt-6 space-y-4">
                  <li className="border-t border-outline-variant pt-4">
                    <p className="font-mono text-[12px] text-on-surface-variant">
                      Step 01 · 0 min
                    </p>
                    <p className="mt-1 text-[15px] font-medium text-on-surface">
                      Upload source media as a draft
                    </p>
                    <p className="mt-1 text-[13px] leading-5 text-on-surface-variant">
                      Set your timeline frame rate and open the multi-track
                      editor immediately.
                    </p>
                  </li>
                  <li className="border-t border-outline-variant pt-4">
                    <p className="font-mono text-[12px] text-on-surface-variant">
                      Step 02 · Pay per effect
                    </p>
                    <p className="mt-1 text-[15px] font-medium text-on-surface">
                      Audition stems and apply effects on demand
                    </p>
                    <p className="mt-1 text-[13px] leading-5 text-on-surface-variant">
                      Mute and unmute tracks in sync, tune studio polish
                      parameters, and switch speaker roles without re-running ASR.
                    </p>
                  </li>
                  <li className="border-t border-outline-variant pt-4">
                    <p className="font-mono text-[12px] text-on-surface-variant">
                      Step 03 · Automatic refunds
                    </p>
                    <p className="mt-1 text-[15px] font-medium text-on-surface">
                      Export stems, SRT captions, and ROUGH-CUT.md
                    </p>
                    <p className="mt-1 text-[13px] leading-5 text-on-surface-variant">
                      Credits reserve when a run starts and refund automatically
                      if any stage fails.
                    </p>
                  </li>
                </ol>
              </div>
            </div>
          </div>
        </section>

        <section className="border-b border-outline-variant bg-surface-container-low px-6 py-20">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
              Ready for the dark suite.
            </h2>
            <p className="mx-auto mt-3 max-w-[46ch] text-[15px] leading-6 text-on-surface-variant">
              Create a free account to run your own shoot audio through the
              pipeline. No card required.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              {me ? (
                <Link
                  to="/"
                  className="inline-flex h-11 items-center rounded-[20px] bg-primary px-6 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9]"
                >
                  Open dashboard
                </Link>
              ) : (
                <>
                  <Link
                    to="/register"
                    className="inline-flex h-11 items-center rounded-[20px] bg-primary px-6 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9]"
                  >
                    Create free account
                  </Link>
                  <Link
                    to="/login"
                    className="inline-flex h-11 items-center rounded-[20px] border border-outline px-5 text-sm font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high"
                  >
                    Sign in
                  </Link>
                </>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-[13px] text-on-surface-variant">
          <div className="flex items-center gap-4">
            <span className="font-mono text-[12px] tracking-[0.22em] text-on-surface">
              PARECUT
            </span>
            <span>AI audio engineering and rough-cut preparation</span>
          </div>
          <div className="flex items-center gap-5">
            <Link
              to="/login"
              className="transition-colors duration-150 ease-standard hover:text-on-surface"
            >
              Sign in
            </Link>
            <Link
              to="/register"
              className="transition-colors duration-150 ease-standard hover:text-on-surface"
            >
              Create account
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
