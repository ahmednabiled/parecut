import type { ReactNode } from "react";

interface AuthLayoutProps {
  title: string;
  subtitle: string;
  children: ReactNode;
}

const PIPELINE = ["Clean", "Enhance", "Separate", "Transcribe", "Cut"];

export default function AuthLayout({ title, subtitle, children }: AuthLayoutProps) {
  return (
    <main className="min-h-screen bg-surface text-on-surface">
      <div className="mx-auto grid min-h-screen max-w-6xl lg:grid-cols-[1.02fr_0.98fr]">
        <section className="hidden flex-col justify-between border-r border-outline-variant px-12 py-12 lg:flex">
          <img
            src="/brand/login-logo.png"
            alt="Pare Cut"
            className="h-24 w-auto self-start"
          />

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

            <ol aria-label="Processing pipeline" className="mt-10 grid grid-cols-5">
              {PIPELINE.map((name, index) => (
                <li key={name} className="flex flex-col">
                  <div className="flex items-center">
                    <span className="size-[7px] shrink-0 rounded-full bg-on-surface" />
                    {index < PIPELINE.length - 1 ? (
                      <span className="h-px flex-1 bg-outline-variant" />
                    ) : null}
                  </div>
                  <span className="mt-3 text-[12px] text-on-surface-variant">{name}</span>
                </li>
              ))}
            </ol>
          </div>

          <p className="text-[13px] text-on-surface-variant">
            AI audio engineering and rough-cut preparation.
          </p>
        </section>

        <section className="flex items-center justify-center px-6 py-12 sm:px-10">
          <div className="w-full max-w-md">
            <div className="mb-10 lg:hidden">
              <img src="/brand/login-logo.png" alt="Pare Cut" className="h-16 w-auto" />
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
