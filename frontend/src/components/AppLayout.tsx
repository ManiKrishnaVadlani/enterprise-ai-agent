import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import {
  Activity, Bot, ChevronDown, ChevronRight, CircleHelp, Command, FileStack,
  LayoutDashboard, LogOut, Menu, MessageSquareText, Settings2, ShieldCheck, X,
} from "lucide-react";
import { api } from "../services/api";
import { useSession } from "../context/SessionContext";

const navigation = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/assistant", label: "AI assistant", icon: Bot },
  { to: "/documents", label: "Knowledge base", icon: FileStack },
  { to: "/conversations", label: "Conversations", icon: MessageSquareText },
];

const titleMap: Record<string, string> = {
  "/": "Overview",
  "/assistant": "AI assistant",
  "/documents": "Knowledge base",
  "/conversations": "Conversations",
  "/settings": "Settings",
};

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout } = useSession();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [apiReady, setApiReady] = useState<boolean | null>(null);
  const title = titleMap[location.pathname] ?? "Workspace";

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        await api.getReadiness();
        if (active) setApiReady(true);
      } catch {
        if (active) setApiReady(false);
      }
    };
    void check();
    const interval = window.setInterval(() => void check(), 30_000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const statusText = useMemo(() => {
    if (apiReady === null) return "Checking API";
    return apiReady ? "API connected" : "API unavailable";
  }, [apiReady]);

  const SidebarContent = ({ onNavigate }: { onNavigate?: () => void }) => (
    <>
      <div className="brand-lockup">
        <div className="brand-mark"><Command size={19} strokeWidth={2.2} /></div>
        <div className="min-w-0">
          <div className="brand-name">Knowledge Agent</div>
          <div className="brand-caption">ENTERPRISE AI</div>
        </div>
        {onNavigate && <button className="icon-button sidebar-close" onClick={onNavigate} aria-label="Close navigation"><X size={18} /></button>}
      </div>

      <div className="workspace-switcher">
        <div className="workspace-avatar">E</div>
        <div className="workspace-copy"><span>Enterprise space</span><small>Personal workspace</small></div>
        <ChevronDown size={15} className="text-slate-500" />
      </div>

      <div className="sidebar-section-label">WORKSPACE</div>
      <nav className="sidebar-nav" aria-label="Main navigation">
        {navigation.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} onClick={onNavigate} className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}>
            <Icon size={18} strokeWidth={1.8} />
            <span>{label}</span>
            {label === "Knowledge base" && <span className="nav-count">KB</span>}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-bottom">
        <div className="security-note">
          <div className="security-icon"><ShieldCheck size={16} /></div>
          <div><strong>Private by design</strong><span>Your workspace is access-controlled.</span></div>
        </div>
        <NavLink to="/settings" onClick={onNavigate} className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}>
          <Settings2 size={18} strokeWidth={1.8} /><span>Settings</span><ChevronRight size={15} className="ml-auto opacity-50" />
        </NavLink>
        <button className="session-card" onClick={() => { logout(); navigate("/login", { replace: true }); }}>
          <div className="session-avatar"><Activity size={16} /></div>
          <div className="session-copy"><strong>Authenticated session</strong><span>Token-based access</span></div>
          <LogOut size={16} className="text-slate-500 transition group-hover:text-white" />
        </button>
        <div className="sidebar-footer"><CircleHelp size={14} /> Local demo environment <span>v1.0</span></div>
      </div>
    </>
  );

  return (
    <div className="app-shell">
      <aside className="desktop-sidebar"><SidebarContent /></aside>
      {mobileOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
      <aside className={`mobile-sidebar ${mobileOpen ? "mobile-sidebar-open" : ""}`}><SidebarContent onNavigate={() => setMobileOpen(false)} /></aside>
      <div className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-menu-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
            <div className="breadcrumbs"><span>Workspace</span><ChevronRight size={13} /><strong>{title}</strong></div>
          </div>
          <div className="topbar-right">
            <div className={`connection-pill ${apiReady ? "connection-online" : apiReady === false ? "connection-offline" : "connection-pending"}`}>
              <span className="connection-dot" />{statusText}
            </div>
            <div className="topbar-divider" />
            <div className="topbar-user"><span className="online-indicator" />Local session</div>
          </div>
        </header>
        <main className="page-content"><Outlet /></main>
      </div>
    </div>
  );
}
