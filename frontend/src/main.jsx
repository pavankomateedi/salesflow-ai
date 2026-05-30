import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import Chat from "./pages/Chat.jsx";
import Voice from "./pages/Voice.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import "./styles.css";

function Shell() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          SalesFlow <span className="accent">AI</span>
          <span className="agent-tag">Vani · vani-v1.0.0</span>
        </div>
        <nav className="nav">
          <NavLink to="/" end>Chat</NavLink>
          <NavLink to="/voice">Voice</NavLink>
          <NavLink to="/dashboard">Dashboard</NavLink>
        </nav>
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<Chat />} />
          <Route path="/voice" element={<Voice />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  </React.StrictMode>
);
