export default function Brand({ size = "md" }: { size?: "md" | "lg" }) {
  const markHeight = size === "lg" ? "h-9" : "h-7";
  return (
    <span className="flex items-center gap-3">
      <img
        src="/brand/logo.png"
        alt=""
        aria-hidden="true"
        className={`${markHeight} w-auto`}
      />
      <span className="font-mono text-xs font-medium tracking-[0.26em] text-on-surface">
        PARECUT
      </span>
    </span>
  );
}
