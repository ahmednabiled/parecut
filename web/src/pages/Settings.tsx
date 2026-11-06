import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { apiFetch } from "../api/client";
import type { ProfileResponse, SessionUser } from "../api/types";

const FPS_OPTIONS = ["24", "25", "29.97", "30", "60"];

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
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal-500">
        Preferences
      </p>
      <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em]">Settings</h1>
      <p className="mt-2 text-sm text-mist-400">
        Defaults apply to new jobs. Existing deliverables are unchanged.
      </p>

      <form onSubmit={save} className="mt-8 space-y-6">
        <section className="rounded-xl border border-ink-700 bg-ink-850 p-5">
          <h2 className="text-sm font-medium text-mist-200">Profile</h2>
          <div className="mt-4">
            <label
              htmlFor="full-name"
              className="mb-2 block font-mono text-[10px] uppercase tracking-[0.16em] text-mist-400"
            >
              Full name
            </label>
            <input
              id="full-name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              className="w-full rounded-lg border border-ink-600 bg-ink-900 px-4 py-2.5 text-sm text-mist-100 outline-none transition focus:border-signal-500 focus:ring-2 focus:ring-signal-500/20"
            />
          </div>
          <p className="mt-3 text-xs text-mist-500">
            Signed in as {profileQuery.data?.user.email ?? "…"}
          </p>
        </section>

        <section className="rounded-xl border border-ink-700 bg-ink-850 p-5">
          <h2 className="text-sm font-medium text-mist-200">Timeline defaults</h2>

          <div className="mt-4">
            <label
              htmlFor="fps"
              className="mb-2 block font-mono text-[10px] uppercase tracking-[0.16em] text-mist-400"
            >
              Frame rate
            </label>
            <select
              id="fps"
              value={fps}
              onChange={(event) => setFps(event.target.value)}
              className="w-full rounded-lg border border-ink-600 bg-ink-900 px-4 py-2.5 text-sm text-mist-100 outline-none focus:border-signal-500"
            >
              {FPS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option} fps
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-mist-500">
              Timecodes in ROUGH-CUT.md snap to this rate.
            </p>
          </div>

          <div className="mt-6">
            <div className="flex items-center justify-between">
              <label
                htmlFor="mix"
                className="font-mono text-[10px] uppercase tracking-[0.16em] text-mist-400"
              >
                Enhancement mix
              </label>
              <span className="font-mono text-xs text-mist-200">{mix}%</span>
            </div>
            <input
              id="mix"
              type="range"
              min={0}
              max={100}
              value={mix}
              onChange={(event) => setMix(Number(event.target.value))}
              className="mt-3 w-full accent-signal-500"
            />
          </div>

          <div className="mt-6">
            <label
              htmlFor="pad"
              className="mb-2 block font-mono text-[10px] uppercase tracking-[0.16em] text-mist-400"
            >
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
              className="w-36 rounded-lg border border-ink-600 bg-ink-900 px-4 py-2.5 font-mono text-sm text-mist-100 outline-none focus:border-signal-500"
            />
          </div>
        </section>

        {notice ? (
          <p className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
            {notice}
          </p>
        ) : null}
        {error ? (
          <p className="rounded-lg border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={saving || profileQuery.isPending}
          className="rounded-lg bg-signal-500 px-5 py-2.5 text-sm font-semibold text-ink-950 transition hover:bg-signal-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save settings"}
        </button>
      </form>
    </div>
  );
}
