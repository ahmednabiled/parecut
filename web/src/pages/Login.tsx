import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, apiFetch } from "../api/client";
import type { SessionUser } from "../api/types";
import AuthLayout from "../components/AuthLayout";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const data = await apiFetch<SessionUser>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      queryClient.setQueryData(["me"], data);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in. Try again.");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthLayout
      eyebrow="Welcome back"
      title="Sign in to Parecut"
      subtitle="Your cuts, stems, and transcripts are waiting."
    >
      <form onSubmit={submit} className="space-y-5" noValidate>
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
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-lg border border-ink-600 bg-ink-900 px-4 py-3 text-sm text-mist-100 outline-none transition focus:border-signal-500 focus:ring-2 focus:ring-signal-500/20"
          />
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
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="mt-7 text-sm text-mist-400">
        New to Parecut?{" "}
        <Link to="/register" className="font-medium text-signal-500 hover:text-signal-400">
          Create an account
        </Link>
      </p>
    </AuthLayout>
  );
}
