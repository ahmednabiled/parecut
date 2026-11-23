import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useMatch, useNavigate } from "react-router-dom";
import { apiFetch } from "../api/client";
import type { ProfileResponse } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import Icon, { type IconName } from "./Icon";

const NAV: { to: string; label: string; icon: IconName; end: boolean }[] = [
  { to: "/", label: "Dashboard", icon: "dashboard", end: true },
  { to: "/new", label: "New project", icon: "add", end: false },
  { to: "/settings", label: "Settings", icon: "settings", end: false },
];

function NavIcon({ name }: { name: IconName }) {
  return <Icon name={name} />;
}

export default function AppShell() {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const editor = useMatch("/jobs/:id");
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    if (!window.matchMedia("(min-width: 1024px)").matches) return false;
    try {
      const stored = window.localStorage.getItem("parecut-sidebar");
      if (stored !== null) return stored === "1";
    } catch {
      // Fall through to the desktop default.
    }
    return true;
  });

  useEffect(() => {
    if (!window.matchMedia("(min-width: 1024px)").matches) return;
    try {
      window.localStorage.setItem("parecut-sidebar", sidebarOpen ? "1" : "0");
    } catch {
      // The sidebar still works without persistence.
    }
  }, [sidebarOpen]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const handleChange = () => {
      if (!media.matches) setSidebarOpen(false);
    };
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, []);

  useEffect(() => {
    if (!editor) return;
    const media = window.matchMedia("(min-width: 1280px)");
    const apply = () => {
      document.documentElement.style.overflow = media.matches
        ? "hidden"
        : "";
      document.body.style.overflow = media.matches ? "hidden" : "";
    };
    apply();
    media.addEventListener("change", apply);
    return () => {
      media.removeEventListener("change", apply);
      document.documentElement.style.overflow = "";
      document.body.style.overflow = "";
    };
  }, [editor]);

  useEffect(() => {
    if (!sidebarOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && window.innerWidth < 1024) {
        setSidebarOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [sidebarOpen]);

  function closeOnMobile() {
    if (window.innerWidth < 1024) setSidebarOpen(false);
  }
  const profileQuery = useQuery<ProfileResponse>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileResponse>("/api/profile"),
  });

  const balance =
    profileQuery.data?.profile.credit_balance_minutes ??
    me?.profile.credit_balance_minutes ??
    0;

  async function signOut() {
    try {
      await apiFetch<void>("/api/auth/logout", { method: "POST" });
    } catch {
      // Clear local session state even if the network request fails.
    } finally {
      queryClient.clear();
      navigate("/login", { replace: true });
    }
  }

  return (
    <div
      className={`flex bg-surface text-on-surface ${
        editor ? "xl:h-screen xl:overflow-hidden" : "min-h-screen"
      }`}
    >
      {sidebarOpen ? (
        <button
          type="button"
          aria-label="Close sidebar"
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
        />
      ) : null}

      <aside
        aria-hidden={!sidebarOpen}
        inert={!sidebarOpen}
        className={`fixed inset-y-0 left-0 z-40 flex w-60 shrink-0 flex-col overflow-hidden border-r border-outline-variant bg-surface-container-low px-3 py-5 transition-transform duration-200 ease-standard lg:static lg:z-auto lg:translate-x-0 lg:transition-[width] ${
          sidebarOpen
            ? "translate-x-0 lg:w-60"
            : "-translate-x-full lg:w-0 lg:border-r-0 lg:px-0"
        }`}
      >
        <div className="flex items-center justify-between gap-2 px-2 py-1">
          <NavLink to="/" onClick={closeOnMobile} className="shrink-0">
            <img
              src="/brand/login-logo.png"
              alt="Parecut"
              className="h-14 w-auto"
            />
          </NavLink>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
            className="grid size-8 shrink-0 place-items-center rounded-full text-on-surface-variant transition-colors duration-150 ease-standard hover:bg-surface-container hover:text-on-surface"
          >
            <NavIcon name="menu_open" />
          </button>
        </div>

        <nav className="mt-8 space-y-1">
          {NAV.map(({ to, label, icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={closeOnMobile}
              className={({ isActive }) =>
                `flex items-center gap-3 whitespace-nowrap rounded-full px-4 py-2.5 text-sm transition-colors duration-150 ease-standard ${
                  isActive
                    ? "bg-surface-container-high text-on-surface"
                    : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
                }`
              }
            >
              <NavIcon name={icon} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto space-y-4">
          <div className="rounded-xl border border-outline-variant bg-surface-container p-4">
            <div className="flex items-center gap-2 text-[13px] text-on-surface-variant">
              <NavIcon name="graphic_eq" />
              Processing credits
            </div>
            <p className="mt-2 font-mono text-2xl font-medium tracking-tight text-on-surface">
              {balance.toFixed(1)}
              <span className="ml-2 font-sans text-xs font-normal tracking-normal text-on-surface-variant">
                minutes
              </span>
            </p>
          </div>

          <div className="flex items-center gap-3 border-t border-outline-variant px-1 pt-4">
            <div className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-container-highest text-[12px] font-medium text-on-surface">
              {(me?.user.full_name || me?.user.email || "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] text-on-surface">{me?.user.full_name}</p>
              <p className="truncate text-[12px] text-on-surface-variant">
                {me?.user.email}
              </p>
            </div>
            <button
              type="button"
              onClick={signOut}
              aria-label="Sign out"
              className="rounded-full p-2 text-on-surface-variant transition-colors duration-150 ease-standard hover:bg-surface-container hover:text-on-surface"
            >
              <NavIcon name="logout" />
            </button>
          </div>
        </div>
      </aside>

      {!sidebarOpen ? (
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          aria-label="Open sidebar"
          className="fixed left-2 top-9 z-40 hidden size-8 place-items-center rounded-md text-on-surface-variant transition-colors duration-150 ease-standard hover:bg-surface-container-high hover:text-on-surface lg:grid"
        >
          <NavIcon name="menu" />
        </button>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-outline-variant px-5 py-4 lg:hidden">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setSidebarOpen((open) => !open)}
              aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
              className="grid size-9 place-items-center rounded-full text-on-surface-variant transition-colors duration-150 ease-standard hover:bg-surface-container hover:text-on-surface"
            >
              <NavIcon name={sidebarOpen ? "close" : "menu"} />
            </button>
            <img
              src="/brand/login-logo.png"
              alt="Parecut"
              className="h-12 w-auto"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[12px] text-on-surface-variant">
              {balance.toFixed(1)} min
            </span>
            <button
              type="button"
              onClick={signOut}
              aria-label="Sign out"
              className="rounded-full p-2 text-on-surface-variant"
            >
              <NavIcon name="logout" />
            </button>
          </div>
        </header>

        <main
          className={
            editor
              ? "min-w-0 flex-1 px-5 py-8 sm:px-8 lg:px-10 xl:flex xl:min-h-0 xl:flex-col xl:overflow-hidden xl:py-4"
              : "min-w-0 flex-1 px-5 py-8 sm:px-8 lg:px-10"
          }
        >
          <div
            className={
              editor
                ? "mx-auto w-full min-w-0 max-w-[1600px] xl:flex xl:min-h-0 xl:flex-1 xl:flex-col"
                : "mx-auto max-w-6xl"
            }
          >
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
