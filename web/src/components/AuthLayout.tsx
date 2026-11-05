import { AudioWaveform, Scissors, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

interface AuthLayoutProps {
  eyebrow: string;
  title: string;
  subtitle: string;
  children: ReactNode;
}

export default function AuthLayout({ eyebrow, title, subtitle, children }: AuthLayoutProps) {
  return (
    <main className="min-h-screen bg-ink-950 text-mist-100">
      <div className="mx-auto grid min-h-screen max-w-6xl lg:grid-cols-[1.05fr_0.95fr]">
        <section className="relative hidden overflow-hidden border-r border-ink-800 px-12 py-14 lg:flex lg:flex-col lg:justify-between">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_18%,rgba(240,162,60,0.16),transparent_38%),radial-gradient(circle_at_80%_80%,rgba(240,162,60,0.06),transparent_45%)]" />
          <div className="relative">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-xl bg-signal-500 text-ink-950">
                <Scissors size={19} strokeWidth={2.2} />
              </span>
              <span className="font-mono text-sm font-semibold tracking-[0.28em] text-mist-100">
                PARECUT
              </span>
            </div>

            <h1 className="mt-20 max-w-md text-4xl font-semibold leading-[1.08] tracking-[-0.03em] text-mist-100">
              The rough cut starts with clean audio.
            </h1>
            <p className="mt-5 max-w-sm text-[15px] leading-7 text-mist-400">
              Denoise, enhance, split speakers, and turn a messy shoot into a
              frame-accurate edit plan your NLE agent can execute.
            </p>

            <ul className="mt-10 space-y-4 text-sm text-mist-200">
              <li className="flex items-center gap-3">
                <AudioWaveform size={17} className="text-signal-500" />
                Studio-clean stems from a single microphone
              </li>
              <li className="flex items-center gap-3">
                <Sparkles size={17} className="text-signal-500" />
                Speaker-attributed, word-aligned transcripts
              </li>
              <li className="flex items-center gap-3">
                <Scissors size={17} className="text-signal-500" />
                Keep/remove ranges ready for Resolve and Premiere
              </li>
            </ul>
          </div>

          <p className="relative font-mono text-[11px] uppercase tracking-[0.18em] text-mist-400">
            AI audio engineering · rough-cut prep
          </p>
        </section>

        <section className="flex items-center justify-center px-6 py-14 sm:px-10">
          <div className="w-full max-w-md">
            <div className="mb-10 flex items-center gap-3 lg:hidden">
              <span className="grid size-9 place-items-center rounded-lg bg-signal-500 text-ink-950">
                <Scissors size={17} strokeWidth={2.2} />
              </span>
              <span className="font-mono text-xs font-semibold tracking-[0.28em]">PARECUT</span>
            </div>

            <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-signal-500">
              {eyebrow}
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.025em] text-mist-100">
              {title}
            </h2>
            <p className="mt-3 text-sm leading-6 text-mist-400">{subtitle}</p>

            <div className="mt-9">{children}</div>
          </div>
        </section>
      </div>
    </main>
  );
}
