import type { ReactNode } from "react";
import Brand from "./Brand";

interface AuthLayoutProps {
  title: string;
  subtitle: string;
  children: ReactNode;
}

const PIPELINE = [
  ["01", "Clean", "Stationary noise, hum, and level"],
  ["02", "Enhance", "Dereverb and voice restoration"],
  ["03", "Separate", "Music and per-speaker stems"],
  ["04", "Transcribe", "Word-level, speaker-attributed"],
  ["05", "Cut", "Frame-accurate ROUGH-CUT.md"],
];

export default function AuthLayout({ title, subtitle, children }: AuthLayoutProps) {
  return (
    <main className="min-h-screen bg-surface text-on-surface">
      <div className="mx-auto grid min-h-screen max-w-6xl lg:grid-cols-[1.02fr_0.98fr]">
        <section className="hidden flex-col justify-between overflow-hidden border-r border-outline-variant px-12 py-12 lg:flex">
          <Brand size="lg" />

          <div className="max-w-[34rem]">
            <h1 className="text-[38px] font-semibold leading-[1.12] tracking-[-0.02em]">
              Clean audio in.
              <br />
              A frame-accurate cut out.
            </h1>
            <p className="mt-5 max-w-sm text-[15px] leading-7 text-on-surface-variant">
              One modular pipeline takes a difficult recording from raw microphone
              audio to stems, a speaker-attributed transcript, and an exact
              keep/remove specification.
            </p>

            <ol className="mt-10 divide-y divide-outline-variant border-y border-outline-variant">
              {PIPELINE.map(([index, name, detail]) => (
                <li
                  key={index}
                  className="grid grid-cols-[2.5rem_1fr] items-baseline gap-3 py-3"
                >
                  <span className="font-mono text-[12px] text-on-surface-variant">
                    {index}
                  </span>
                  <span>
                    <span className="text-sm font-medium text-on-surface">{name}</span>
                    <span className="ml-2 text-[13px] text-on-surface-variant">
                      {detail}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </div>

          <div>
            <p className="text-[13px] text-on-surface-variant">
              AI audio engineering and rough-cut preparation.
            </p>
            <div className="-mx-12 -mb-12 mt-6 hidden [@media(min-height:960px)]:block">
              <img
                src="/brand/cover.webp"
                alt=""
                aria-hidden="true"
                className="h-44 w-full object-cover object-center grayscale"
              />
            </div>
          </div>
        </section>

        <section className="flex items-center justify-center px-6 py-12 sm:px-10">
          <div className="w-full max-w-md">
            <div className="mb-10 lg:hidden">
              <Brand />
            </div>

            <h2 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
              {title}
            </h2>
            <p className="mt-3 max-w-sm text-[15px] leading-6 text-on-surface-variant">
              {subtitle}
            </p>

            <div className="mt-9">{children}</div>
          </div>
        </section>
      </div>
    </main>
  );
}
