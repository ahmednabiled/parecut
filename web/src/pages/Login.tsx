import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, apiFetch } from "../api/client";
import type { SessionUser } from "../api/types";
import AuthLayout from "../components/AuthLayout";
import Icon from "../components/Icon";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/";

  async function loginWith(targetEmail: string, targetPassword: string) {
    setError(null);
    setPending(true);
    try {
      const data = await apiFetch<SessionUser>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: targetEmail, password: targetPassword }),
      });
      queryClient.setQueryData(["me"], data);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to sign in. Try again.");
    } finally {
      setPending(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void loginWith(email, password);
  }

  function signInDemo() {
    setEmail("demo@parecut.app");
    setPassword("parecut-demo");
    void loginWith("demo@parecut.app", "parecut-demo");
  }

  return (
    <AuthLayout
      title="Sign in to Parecut"
      subtitle="Your jobs, stems, and cut specifications are waiting."
    >
      <form onSubmit={submit} className="space-y-5" noValidate>
        <div>
          <label
            htmlFor="email"
            className="mb-2 block text-[13px] font-medium text-on-surface-variant"
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
            className="h-12 w-full rounded border border-outline bg-transparent px-4 text-[15px] text-on-surface transition-[border-color,background-color] duration-150 ease-standard hover:border-on-surface-variant focus:border-on-surface"
          />
        </div>

        <div>
          <label
            htmlFor="password"
            className="mb-2 block text-[13px] font-medium text-on-surface-variant"
          >
            Password
          </label>
          <div className="relative">
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              required
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="h-12 w-full rounded border border-outline bg-transparent pl-4 pr-11 text-[15px] text-on-surface transition-[border-color,background-color] duration-150 ease-standard hover:border-on-surface-variant focus:border-on-surface"
            />
            <button
              type="button"
              onClick={() => setShowPassword((current) => !current)}
              aria-label={showPassword ? "Hide characters" : "Show characters"}
              className="absolute right-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-full text-on-surface-variant transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface"
            >
              <Icon
                name={showPassword ? "visibility_off" : "visibility"}
                size={18}
              />
            </button>
          </div>
        </div>

        {error ? (
          <p
            role="alert"
            className="rounded-lg border border-error/25 bg-error-container px-4 py-3 text-sm text-on-error-container"
          >
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={pending}
          className="h-11 w-full rounded-[20px] bg-primary px-6 text-sm font-semibold text-on-primary transition-colors duration-150 ease-standard hover:bg-[#dcdcdc] active:bg-[#c9c9c9] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? "Signing in…" : "Sign in"}
        </button>

        <button
          type="button"
          disabled={pending}
          onClick={signInDemo}
          className="h-11 w-full rounded-[20px] border border-outline px-6 text-sm font-medium text-on-surface transition-colors duration-150 ease-standard hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-50"
        >
          Use demo account
        </button>
      </form>

      <p className="mt-7 text-sm text-on-surface-variant">
        New to Parecut?{" "}
        <Link
          to="/register"
          className="font-medium text-on-surface underline decoration-outline underline-offset-4 transition-colors duration-150 ease-standard hover:decoration-on-surface"
        >
          Create an account
        </Link>
      </p>
    </AuthLayout>
  );
}
