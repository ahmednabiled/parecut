import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../api/client";
import type { ProfileResponse, SessionUser } from "../api/types";

const FPS_OPTIONS = ["24", "25", "29.97", "30", "50", "60"];

const fieldClass =
  "h-12 w-full rounded border border-outline bg-transparent px-4 text-[15px] text-on-surface transition-[border-color,background-color] duration-150 ease-standard hover:border-on-surface-variant focus:border-on-surface";

const labelClass = "mb-2 block text-[13px] font-medium text-on-surface-variant";

interface SettingsDraft {
  fullName: string;
  fps: string;
  mix: number;
  pad: number;
}

export default function Settings() {
  const queryClient = useQueryClient();
  const profileQuery = useQuery<ProfileResponse>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileResponse>("/api/profile"),
  });

  const [draft, setDraft] = useState<SettingsDraft | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const saved = profileQuery.data;
  const current: SettingsDraft = draft ?? {
    fullName: saved?.user.full_name ?? "",
    fps: saved?.profile.default_fps ?? "25",
    mix: saved?.profile.default_enhance_mix ?? 80,
    pad: saved?.profile.default_silence_pad_ms ?? 150,
  };
  const { fullName, fps, mix, pad } = current;

  function updateDraft(patch: Partial<SettingsDraft>) {
    setDraft({ ...current, ...patch });
    setNotice(null);
    setError(null);
  }

  const isDirty = Boolean(
    saved &&
      (fullName !== saved.user.full_name ||
        fps !== saved.profile.default_fps ||
        mix !== saved.profile.default_enhance_mix ||
        pad !== saved.profile.default_silence_pad_ms),
  );

  function reset() {
    setDraft(null);
    setNotice(null);
    setError(null);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!fullName.trim()) {
      setError("Full name cannot be empty.");
      return;
    }
    setSaving(true);
    setNotice(null);
    setError(null);
    try {
      const data = await apiFetch<ProfileResponse>("/api/profile", {
        method: "PATCH",
        body: JSON.stringify({
          full_name: fullName.trim(),
          default_fps: fps,
          default_enhance_mix: mix,
          default_silence_pad_ms: Math.max(0, Math.min(2000, Math.round(pad))),
        }),
      });
      queryClient.setQueryData(["profile"], data);
      queryClient.setQueryData<SessionUser | undefined>(["me"], (prev) =>
        prev ? { ...prev, user: data.user, profile: data.profile } : prev,
      );
      setDraft(null);
      setNotice("Settings saved.");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not save your settings. Try again.",
      );
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

      {profileQuery.isError ? (
        <div
          role="alert"
          className="mt-8 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-error/25 bg-error-container px-4 py-3 text-sm text-on-error-container"
        >
          <p>Could not load your settings. Try again.</p>
          <button
            type="button"
            onClick={() => void profileQuery.refetch()}
            className="inline-flex h-8 items-center rounded-[16px] border border-error/30 px-3 text-[12px] font-medium text-on-error-container transition-colors duration-150 ease-standard hover:bg-error/15"
          >
            Retry
          </button>
        </div>
      ) : (
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
                  disabled={profileQuery.isPending || saving}
                  onChange={(event) =>
                    updateDraft({ fullName: event.target.value })
                  }
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
                  disabled={profileQuery.isPending || saving}
                  onChange={(event) => updateDraft({ fps: event.target.value })}
                  className="h-12 w-full rounded border border-outline bg-surface-container-low px-4 text-[15px] text-on-surface transition-[border-color,background-color] duration-150 ease-standard hover:border-on-surface-variant focus:border-on-surface"
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
                  disabled={profileQuery.isPending || saving}
                  onChange={(event) =>
                    updateDraft({ mix: Number(event.target.value) })
                  }
                  className="mt-3 w-full accent-primary"
                />
                <div className="mt-1 flex justify-between font-mono text-[11px] text-on-surface-variant">
                  <span>0% · Dry</span>
                  <span>100% · Restored</span>
                </div>
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
                  disabled={profileQuery.isPending || saving}
                  onChange={(event) => {
                    const next = Number(event.target.value);
                    if (Number.isFinite(next)) updateDraft({ pad: next });
                  }}
                  className="h-12 w-36 rounded border border-outline bg-transparent px-4 font-mono text-[15px] text-on-surface transition-[border-color,background-color] duration-150 ease-standard hover:border-on-surface-variant focus:border-on-surface"
                />
              </div>
            </section>
          </div>

          {notice ? (
            <p
              role="status"
              className="mt-5 rounded-lg bg-surface-container-high px-4 py-3 text-sm text-on-surface"
            >
              {notice}
            </p>
          ) : null}
          {error ? (
            <p
              role="alert"
              className="mt-5 rounded-lg border border-error/25 bg-error-container px-4 py-3 text-sm text-on-error-container"
            >
              {error}
            </p>
          ) : null}

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={!isDirty || saving || profileQuery.isPending}
              className="h-10 rounded-[20px] bg-primary px-5 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save settings"}
            </button>
            {isDirty ? (
              <>
                <button
                  type="button"
                  onClick={reset}
                  disabled={saving}
                  className="h-10 rounded-[20px] border border-outline px-4 text-sm font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high disabled:opacity-50"
                >
                  Reset
                </button>
                <span className="text-[12px] text-on-surface-variant">
                  Unsaved changes
                </span>
              </>
            ) : null}
          </div>
        </form>
      )}
    </div>
  );
}
