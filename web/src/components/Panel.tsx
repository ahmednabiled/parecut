import type { ReactNode } from "react";

export default function Panel({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-outline-variant bg-surface-container p-6">
      <h2 className="text-[15px] font-medium text-on-surface">{title}</h2>
      {description ? (
        <p className="mt-1 max-w-[52ch] text-[13px] leading-5 text-on-surface-variant">
          {description}
        </p>
      ) : null}
      <div className="mt-5">{children}</div>
    </section>
  );
}
