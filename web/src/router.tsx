import { Navigate, Route, Routes } from "react-router-dom";
import RequireAuth from "./auth/RequireAuth";
import AppShell from "./components/AppShell";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Settings from "./pages/Settings";

function Placeholder({ title, detail }: { title: string; detail: string }) {
  return (
    <div>
      <h1 className="text-3xl font-semibold tracking-[-0.03em]">{title}</h1>
      <p className="mt-3 max-w-lg text-sm leading-6 text-mist-400">{detail}</p>
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
        <Route
          path="new"
          element={
            <Placeholder
              title="New job"
              detail="Upload a recording, choose pipeline steps, and run the mock pipeline. This screen arrives in the next task."
            />
          }
        />
        <Route
          path="jobs/:id"
          element={
            <Placeholder
              title="Job detail"
              detail="Stage progress, speaker roles, transcripts, and downloads will appear here."
            />
          }
        />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
