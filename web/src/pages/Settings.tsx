import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { apiFetch } from "../api/client";
import type { ProfileResponse, SessionUser } from "../api/types";

const FPS_OPTIONS = ["24", "25", "29.97", "30", "60"];

const fieldClass =
  "h-12 w-full rounded border border-outline bg-transparent px-4 text-[15px] text-on-surface transition-[border-color,background-color] duration-150 ease-standard hover:border-on-surface-variant focus:border-on-surface";

const labelClass = "mb-2 block text-[13px] font-medium text-on-surface-variant";

export default function Settings() {
  const queryClient = useQueryClient();
  const profileQuery = useQuery<ProfileResponse>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileResponse>("/api/profile"),
  });

  const [fullName, setFullName] = useState("");
  const [fps, setFps] = useState("25");
  const [mix, setMix] = useState(80);
  const [pad, setPad] = useState(150);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const data = profileQuery.data;
    if (!data) return;
    setFullName(data.user.full_name);
    setFps(data.profile.default_fps);
    setMix(data.profile.default_enhance_mix);
    setPad(data.profile.default_silence_pad_ms);
  }, [profileQuery.data]);

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setNotice(null);
    setError(null);
    try {
      const data = await apiFetch<ProfileResponse>("/api/profile", {
        method: "PATCH",
        body: JSON.stringify({
          full_name: fullName,
          default_fps: fps,
          default_enhance_mix: mix,
          default_silence_pad_ms: pad,
        }),
      });
      queryClient.setQueryData(["profile"], data);
      queryClient.setQueryData<SessionUser | undefined>(["me"], (current) =>
        current ? { ...current, profile: data.profile } : current,
      );
      setNotice("Settings saved.");
    } catch {
      setError("Could not save your settings. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
        Settings
      </h1>
      <p className="mt-2 max-w-[52ch] text-[15px] leading-6 text-on-surface-variant">
        Defaults apply to new projects. Existing deliverables are unchanged.
      </p>

      <form onSubmit={save} className="mt-8">
        <div className="divide-y divide-outline-variant rounded-xl border border-outline-variant bg-surface-container">
          <section className="p-6">
            <h2 className="text-[15px] font-medium text-on-surface">Profile</h2>
            <div className="mt-4">
              <label htmlFor="full-name" className={labelClass}>
                Full name
              </label>
              <input
                id="full-name"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                className={fieldClass}
              />
            </div>
            <p className="mt-3 text-[13px] text-on-surface-variant">
              Signed in as {profileQuery.data?.user.email ?? "…"}
            </p>
          </section>

          <section className="p-6">
            <h2 className="text-[15px] font-medium text-on-surface">
              Timeline defaults
            </h2>

            <div className="mt-4">
              <label htmlFor="fps" className={labelClass}>
                Frame rate
              </label>
              <select
                id="fps"
                value={fps}
                onChange={(event) => setFps(event.target.value)}
                className={fieldClass}
              >
                {FPS_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option} fps
                  </option>
                ))}
              </select>
              <p className="mt-2 text-[13px] text-on-surface-variant">
                Timecodes in ROUGH-CUT.md snap to this rate.
              </p>
            </div>

            <div className="mt-6">
              <div className="flex items-center justify-between">
                <label htmlFor="mix" className={labelClass}>
                  Enhancement mix
                </label>
                <span className="font-mono text-[13px] text-on-surface">{mix}%</span>
              </div>
              <input
                id="mix"
                type="range"
                min={0}
                max={100}
                value={mix}
                onChange={(event) => setMix(Number(event.target.value))}
                className="mt-3 w-full accent-primary"
              />
            </div>

            <div className="mt-6">
              <label htmlFor="pad" className={labelClass}>
                Breath pad (ms)
              </label>
              <input
                id="pad"
                type="number"
                min={0}
                max={2000}
                step={10}
                value={pad}
                onChange={(event) => setPad(Number(event.target.value))}
                className="h-12 w-36 rounded border border-outline bg-transparent px-4 font-mono text-[15px] text-on-surface transition-[border-color,background-color] duration-150 ease-standard hover:border-on-surface-variant focus:border-on-surface"
              />
            </div>
          </section>
        </div>

        {notice ? (
          <p className="mt-5 rounded-lg bg-surface-container-high px-4 py-3 text-sm text-on-surface">
            {notice}
          </p>
        ) : null}
        {error ? (
          <p className="mt-5 rounded-lg border border-error/25 bg-error-container px-4 py-3 text-sm text-on-error-container">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={saving || profileQuery.isPending}
          className="mt-6 h-10 rounded-[20px] bg-primary px-5 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save settings"}
        </button>
      </form>
    </div>
  );
}
