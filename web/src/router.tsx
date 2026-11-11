import { Navigate, Route, Routes } from "react-router-dom";
import RequireAuth from "./auth/RequireAuth";
import AppShell from "./components/AppShell";
import Dashboard from "./pages/Dashboard";
import JobEditor from "./pages/JobEditor";
import Login from "./pages/Login";
import NewJob from "./pages/NewJob";
import Register from "./pages/Register";
import Settings from "./pages/Settings";

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
        <Route path="jobs/:id" element={<JobEditor />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
