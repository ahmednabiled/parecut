import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthProvider";
import RequireAuth from "./auth/RequireAuth";
import AppShell from "./components/AppShell";
import Dashboard from "./pages/Dashboard";
import JobEditor from "./pages/JobEditor";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import NewJob from "./pages/NewJob";
import Register from "./pages/Register";
import Settings from "./pages/Settings";

function HomeRoute() {
  const { me, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="grid min-h-screen place-items-center bg-surface">
        <span className="spinner" role="status" aria-label="Loading" />
      </div>
    );
  }

  return me ? <AppShell /> : <Landing />;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/landing" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/" element={<HomeRoute />}>
        <Route index element={<Dashboard />} />
      </Route>
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="new" element={<NewJob />} />
        <Route path="jobs/:id" element={<JobEditor />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
