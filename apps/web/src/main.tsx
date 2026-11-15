import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./styles.css";
import { Layout } from "./components/Layout";
import { AuthProvider, useAuth } from "./lib/auth";
import Login from "./app/Login";
import Onboarding from "./app/Onboarding";
import Inbox from "./app/Inbox";
import JobDetail from "./app/JobDetail";
import Studio from "./app/Studio";
import Pipeline from "./app/Pipeline";
import Messages from "./app/Messages";
import RunView from "./app/RunView";
import Analytics from "./app/Analytics";
import Settings from "./app/Settings";

function Guard({ children }: { children: JSX.Element }) {
  const { me, loading } = useAuth();
  if (loading) return <p className="pad" role="status">Loading…</p>;
  if (!me) return <Navigate to="/login" replace />;
  if (!me.onboarded) return <Navigate to="/onboarding" replace />;
  return children;
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/onboarding" element={<Onboarding />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Guard><Inbox /></Guard>} />
        <Route path="/jobs/:id" element={<Guard><JobDetail /></Guard>} />
        <Route path="/studio/:id" element={<Guard><Studio /></Guard>} />
        <Route path="/pipeline" element={<Guard><Pipeline /></Guard>} />
        <Route path="/messages" element={<Guard><Messages /></Guard>} />
        <Route path="/runs/:id" element={<Guard><RunView /></Guard>} />
        <Route path="/analytics" element={<Guard><Analytics /></Guard>} />
        <Route path="/settings" element={<Guard><Settings /></Guard>} />
      </Route>
    </Routes>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider><App /></AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
