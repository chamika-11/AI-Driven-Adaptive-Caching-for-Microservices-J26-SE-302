// ─────────────────────────────────────────────────────────────────────────────
// App Layout Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Shell layout organizing sidebar, top header, and responsive main viewport.
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState } from "react";
import { Sidebar, type NavTab } from "./Sidebar.js";
import { Header } from "./Header.js";

interface AppLayoutProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  title: string;
  subtitle: string;
  isRefreshing: boolean;
  onRefresh: () => void;
  systemStatus?: {
    connected: boolean;
    database?: string;
  } | null;
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  activeTab,
  onSelectTab,
  title,
  subtitle,
  isRefreshing,
  onRefresh,
  systemStatus,
  children,
}) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  return (
    <div className="app-shell">
      <Sidebar
        activeTab={activeTab}
        onSelectTab={onSelectTab}
        isOpenOnMobile={isMobileMenuOpen}
        onCloseMobile={() => setIsMobileMenuOpen(false)}
      />

      <div className="app-main-viewport">
        <Header
          title={title}
          subtitle={subtitle}
          isRefreshing={isRefreshing}
          onRefresh={onRefresh}
          systemStatus={systemStatus}
          onToggleMobileMenu={() => setIsMobileMenuOpen((prev) => !prev)}
        />

        <main className="app-content-area" id="main-content">
          {children}
        </main>
      </div>
    </div>
  );
};
