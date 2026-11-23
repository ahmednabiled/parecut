import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, apiFetch } from "../api/client";
import type { SessionUser } from "../api/types";
import AuthLayout from "../components/AuthLayout";
import Icon from "../components/Icon";

export default function Register() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmedName = fullName.trim();
    const trimmedEmail = email.trim();
    if (!trimmedName) {
      setError("Enter your full name.");
      return;
    }
    if (!trimmedEmail || !trimmedEmail.includes("@")) {
      setError("Enter a valid email address.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setError(null);
    setPending(true);
    try {
      const data = await apiFetch<SessionUser>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          full_name: trimmedName,
          email: trimmedEmail,
          password,
        }),
      });
      queryClient.setQueryData(["me"], data);
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to create your account.");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthLayout
      title="Create your workspace"
      subtitle="Thirty minutes of processing are included. No card required."
    >
      <form onSubmit={submit} className="space-y-5" noValidate>
        <div>
          <label
            htmlFor="full-name"
            className="mb-2 block text-[13px] font-medium text-on-surface-variant"
          >
            Full name
          </label>
          <input
            id="full-name"
            required
            autoComplete="name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            className="h-12 w-full rounded border border-outline bg-transparent px-4 text-[15px] text-on-surface transition-[border-color,background-color] duration-150 ease-standard hover:border-on-surface-variant focus:border-on-surface"
          />
        </div>

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
              minLength={8}
              autoComplete="new-password"
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
          <p className="mt-2 text-xs text-on-surface-variant">At least 8 characters.</p>
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
          {pending ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-7 text-sm text-on-surface-variant">
        Already have an account?{" "}
        <Link
          to="/login"
          className="font-medium text-on-surface underline decoration-outline underline-offset-4 transition-colors duration-150 ease-standard hover:decoration-on-surface"
        >
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
