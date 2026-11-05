import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, apiFetch } from "../api/client";
import type { SessionUser } from "../api/types";
import AuthLayout from "../components/AuthLayout";

export default function Register() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const data = await apiFetch<SessionUser>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          full_name: fullName,
          email,
          password,
        }),
      });
      queryClient.setQueryData(["me"], data);
      queryClient.invalidateQueries({ queryKey: ["profile"] });
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to create your account.");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthLayout
      eyebrow="Get started"
      title="Create your workspace"
      subtitle="Thirty minutes of processing are included. No card required."
    >
      <form onSubmit={submit} className="space-y-5" noValidate>
        <div>
          <label
            htmlFor="full-name"
            className="mb-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-mist-400"
          >
            Full name
          </label>
          <input
            id="full-name"
            required
            autoComplete="name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            className="w-full rounded-lg border border-ink-600 bg-ink-900 px-4 py-3 text-sm text-mist-100 outline-none transition focus:border-signal-500 focus:ring-2 focus:ring-signal-500/20"
          />
        </div>

        <div>
          <label
            htmlFor="email"
            className="mb-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-mist-400"
          >
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="w-full rounded-lg border border-ink-600 bg-ink-900 px-4 py-3 text-sm text-mist-100 outline-none transition focus:border-signal-500 focus:ring-2 focus:ring-signal-500/20"
          />
        </div>

        <div>
          <label
            htmlFor="password"
            className="mb-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-mist-400"
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-lg border border-ink-600 bg-ink-900 px-4 py-3 text-sm text-mist-100 outline-none transition focus:border-signal-500 focus:ring-2 focus:ring-signal-500/20"
          />
          <p className="mt-2 text-xs text-mist-400">At least 8 characters.</p>
        </div>

        {error ? (
          <p
            role="alert"
            className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200"
          >
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-lg bg-signal-500 px-4 py-3 text-sm font-semibold text-ink-950 transition hover:bg-signal-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-7 text-sm text-mist-400">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-signal-500 hover:text-signal-400">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
