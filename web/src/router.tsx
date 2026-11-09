import { Navigate, Route, Routes } from "react-router-dom";
import RequireAuth from "./auth/RequireAuth";
import AppShell from "./components/AppShell";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import NewJob from "./pages/NewJob";
import Register from "./pages/Register";
import Settings from "./pages/Settings";

function ComingSoon({ title, detail }: { title: string; detail: string }) {
  return (
    <div>
      <h1 className="text-[32px] font-semibold leading-10 tracking-[-0.02em]">
        {title}
      </h1>
      <div className="mt-8 max-w-xl rounded-xl border border-outline-variant bg-surface-container p-6">
        <p className="text-[13px] font-medium text-on-surface-variant">Coming soon</p>
        <p className="mt-2 text-[15px] leading-6 text-on-surface">{detail}</p>
      </div>
    </div>
  );
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="new" element={<NewJob />} />
        <Route
          path="jobs/:id"
          element={
            <ComingSoon
              title="Job detail"
              detail="Stage progress, speaker roles, transcripts, and downloads arrive in the next build."
            />
          }
        />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
