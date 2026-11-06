import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AudioLines,
  LayoutDashboard,
  LogOut,
  Plus,
  Scissors,
  Settings as SettingsIcon,
} from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { apiFetch } from "../api/client";
import type { ProfileResponse } from "../api/types";
import { useAuth } from "../auth/AuthProvider";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/new", label: "New job", icon: Plus, end: false },
  { to: "/settings", label: "Settings", icon: SettingsIcon, end: false },
];

export default function AppShell() {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const profileQuery = useQuery<ProfileResponse>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileResponse>("/api/profile"),
  });

  const balance =
    profileQuery.data?.profile.credit_balance_minutes ??
    me?.profile.credit_balance_minutes ??
    0;

  async function signOut() {
    await apiFetch<void>("/api/auth/logout", { method: "POST" });
    queryClient.clear();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-screen bg-ink-950 text-mist-100">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-ink-800 bg-ink-900/60 px-4 py-6 lg:flex">
        <NavLink to="/" className="flex items-center gap-3 px-2">
          <span className="grid size-9 place-items-center rounded-lg bg-signal-500 text-ink-950">
            <Scissors size={17} strokeWidth={2.2} />
          </span>
          <span className="font-mono text-xs font-semibold tracking-[0.26em]">
            PARECUT
          </span>
        </NavLink>

        <nav className="mt-10 space-y-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                  isActive
                    ? "bg-ink-800 text-mist-100"
                    : "text-mist-400 hover:bg-ink-850 hover:text-mist-200"
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto space-y-4">
          <div className="rounded-xl border border-ink-700 bg-ink-850 p-4">
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-mist-400">
              <AudioLines size={12} className="text-signal-500" />
              Credits
            </div>
            <p className="mt-2 text-2xl font-semibold tracking-tight">
              {balance.toFixed(1)}
              <span className="ml-1 text-xs font-normal text-mist-400">min</span>
            </p>
          </div>

          <div className="flex items-center gap-3 border-t border-ink-800 px-1 pt-4">
            <div className="grid size-8 shrink-0 place-items-center rounded-full bg-ink-700 font-mono text-[11px] text-mist-200">
              {(me?.user.full_name || me?.user.email || "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs text-mist-200">{me?.user.full_name}</p>
              <p className="truncate text-[11px] text-mist-500">{me?.user.email}</p>
            </div>
            <button
              type="button"
              onClick={signOut}
              aria-label="Sign out"
              className="rounded-md p-2 text-mist-400 transition hover:bg-ink-800 hover:text-mist-100"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-ink-800 px-5 py-4 lg:hidden">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-signal-500 text-ink-950">
              <Scissors size={15} />
            </span>
            <span className="font-mono text-[11px] font-semibold tracking-[0.24em]">
              PARECUT
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[11px] text-mist-400">
              {balance.toFixed(1)} min
            </span>
            <button
              type="button"
              onClick={signOut}
              aria-label="Sign out"
              className="rounded-md p-2 text-mist-400"
            >
              <LogOut size={15} />
            </button>
          </div>
        </header>

        <main className="flex-1 px-5 py-8 sm:px-8 lg:px-10">
          <div className="mx-auto max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
