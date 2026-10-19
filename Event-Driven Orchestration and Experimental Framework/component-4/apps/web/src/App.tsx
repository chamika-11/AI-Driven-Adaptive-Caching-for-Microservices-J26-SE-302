// ─────────────────────────────────────────────────────────────────────────────
// Main Application Component — Component 4 Web
// "Event Intelligence & Context-Aware Feature Engineering"
//
// Root dashboard entry point supporting sidebar navigation, live system health,
// and state synchronization across views.
// ─────────────────────────────────────────────────────────────────────────────

import { useState, useEffect, useCallback } from "react";
import { AppLayout } from "./components/layout/AppLayout.js";
import { type NavTab } from "./components/layout/Sidebar.js";
import { DashboardPage } from "./pages/DashboardPage.js";
import { PlaceholderView } from "./components/dashboard/PlaceholderView.js";
import { ApiDocIngestionView } from "./components/dashboard/ApiDocIngestionView.js";
import { getSystemReadiness } from "./services/events.service.js";

export function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("dashboard");
  const [refreshTrigger, setRefreshTrigger] = useState<number>(0);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [systemStatus, setSystemStatus] = useState<{
    connected: boolean;
    database?: string;
  } | null>(null);

  /**
   * Checks backend and database readiness.
   */
  const checkHealth = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await getSystemReadiness(signal);
      setSystemStatus({
        connected: res.status === "ok",
        database: res.database,
      });
    } catch {
      setSystemStatus({
        connected: false,
      });
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    checkHealth(controller.signal);

    // Re-check health every 30 seconds
    const interval = setInterval(() => {
      checkHealth();
    }, 30000);

    return () => {
      controller.abort();
      clearInterval(interval);
    };
  }, [checkHealth]);

  /**
   * Refreshes dashboard data and re-verifies system health.
   */
  const handleRefresh = async () => {
    setIsRefreshing(true);
    setRefreshTrigger((prev) => prev + 1);
    await checkHealth();
    // Brief transition for UI feedback
    setTimeout(() => {
      setIsRefreshing(false);
    }, 400);
  };

  const getPageMeta = (tab: NavTab) => {
    switch (tab) {
      case "dashboard":
        return {
          title: "Event Intelligence Dashboard",
          subtitle: "Component 4 — AI-Based Adaptive Caching Experimental Framework",
        };
      case "events":
        return {
          title: "Scheduled Business Events",
          subtitle: "Temporal event catalogue & microservice impact windows",
        };
      case "api-docs":
        return {
          title: "API Documentation",
          subtitle: "OpenAPI endpoints & service contract repository",
        };
      case "settings":
        return {
          title: "System Settings",
          subtitle: "Framework preferences, feature weights, and prewarm heuristics",
        };
      default:
        return {
          title: "Dashboard",
          subtitle: "Event Intelligence & Context-Aware Feature Engineering",
        };
    }
  };

  const { title, subtitle } = getPageMeta(activeTab);

  return (
    <AppLayout
      activeTab={activeTab}
      onSelectTab={setActiveTab}
      title={title}
      subtitle={subtitle}
      isRefreshing={isRefreshing}
      onRefresh={handleRefresh}
      systemStatus={systemStatus}
    >
      {activeTab === "dashboard" || activeTab === "events" ? (
        <DashboardPage refreshTrigger={refreshTrigger} />
      ) : activeTab === "api-docs" ? (
        <ApiDocIngestionView onBackToDashboard={() => setActiveTab("dashboard")} />
      ) : (
        <PlaceholderView
          tab={activeTab}
          onBackToDashboard={() => setActiveTab("dashboard")}
        />
      )}
    </AppLayout>
  );
}
