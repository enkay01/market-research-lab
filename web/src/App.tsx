import { FormEvent, useEffect, useState } from "react";
import {
  AppShell,
  TopNav,
  TopNavItem,
  TopNavHeading,
  HStack,
  VStack,
  Button,
  StatusDot,
  Text,
  Dialog,
  DialogHeader,
  TextInput,
  Banner,
  Selector,
} from "@astryxdesign/core";
import { api, type Project } from "./api/client";
import { DataView } from "./views/DataView";
import { ResearchView } from "./views/ResearchView";
import { ValuationView } from "./views/ValuationView";
import { ModelsView } from "./views/ModelsView";
import { BacktestView } from "./views/BacktestView";
import { AlertsView } from "./views/AlertsView";
import { StudyView } from "./views/StudyView";
import { CleanupView } from "./views/CleanupView";

export type DomainTab =
  | "data"
  | "research"
  | "valuation"
  | "models"
  | "backtest"
  | "alerts"
  | "study"
  | "cleanup";

export function App() {
  const [activeTab, setActiveTab] = useState<DomainTab>(() => {
    const params = new URLSearchParams(window.location.search);
    // SAFETY: Query param tab is validated against known domain tab strings below
    const tabParam = params.get("tab") as DomainTab | null;
    const hasVariant = params.has("variant");
    if (hasVariant || tabParam === "backtest") {
      return "backtest";
    }
    if (tabParam && ["data", "research", "valuation", "models", "backtest", "alerts", "study", "cleanup"].includes(tabParam)) {
      return tabParam;
    }
    return "data";
  });
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | undefined>();
  const [engineConnected, setEngineConnected] = useState(false);
  const [statusText, setStatusText] = useState("Connecting…");
  const [focusSecurityId, setFocusSecurityId] = useState<string | null>(null);

  function openSecurity(securityId: string) {
    setFocusSecurityId(securityId);
    setActiveTab("research");
  }

  // Project Creation Modal
  const [isNewProjectOpen, setIsNewProjectOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([api.health(), api.listProjects()])
      .then(([health, availableProjects]) => {
        setProjects(availableProjects);
        if (availableProjects.length > 0) {
          setSelectedProject(availableProjects[0]);
        }
        const isOk = health.status === "ok";
        setEngineConnected(isOk);
        setStatusText(isOk ? "Engine Online" : "Engine Unavailable");
      })
      .catch((cause: unknown) => {
        setEngineConnected(false);
        setStatusText(cause instanceof Error ? cause.message : "Engine Offline");
      });
  }, []);

  async function handleCreateProject(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!newProjectName.trim()) return;

    setIsCreatingProject(true);
    setProjectError(null);
    try {
      const created = await api.createProject({ name: newProjectName.trim() });
      setProjects((prev) => [created, ...prev]);
      setSelectedProject(created);
      setNewProjectName("");
      setIsNewProjectOpen(false);
    } catch (err: unknown) {
      setProjectError(err instanceof Error ? err.message : "Failed to create project.");
    } finally {
      setIsCreatingProject(false);
    }
  }

  function handleProjectDeleted(projectId: string) {
    const remaining = projects.filter((project) => project.id !== projectId);
    setProjects(remaining);
    setSelectedProject(remaining[0]);
    setActiveTab("data");
  }

  const projectOptions = projects.map((p) => ({
    value: p.id,
    label: p.name,
  }));

  return (
    <AppShell
      height="fill"
      contentPadding={0}
      topNav={
        <TopNav
          label="Market Research Lab Navigation"
          heading={
            <TopNavHeading>
              <HStack align="center" gap={2}>
                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "26px",
                    height: "26px",
                    borderRadius: "var(--radius-sm, 4px)",
                    backgroundColor: "var(--color-accent-purple, #6e40c9)",
                    color: "#ffffff",
                    fontWeight: 800,
                    fontSize: "13px",
                    userSelect: "none",
                  }}
                >
                  M
                </div>
                <Text weight="bold">
                  Market Research Lab
                </Text>
              </HStack>
            </TopNavHeading>
          }
          startContent={
            <HStack gap={1}>
              <TopNavItem
                label="Market Data"
                isSelected={activeTab === "data"}
                onClick={() => setActiveTab("data")}
                as="button"
              />
              <TopNavItem
                label="Security Research"
                isSelected={activeTab === "research"}
                onClick={() => setActiveTab("research")}
                as="button"
              />
              <TopNavItem
                label="Valuation"
                isSelected={activeTab === "valuation"}
                onClick={() => setActiveTab("valuation")}
                as="button"
              />
              <TopNavItem
                label="Models & Indicators"
                isSelected={activeTab === "models"}
                onClick={() => setActiveTab("models")}
                as="button"
              />
              <TopNavItem
                label="Backtests"
                isSelected={activeTab === "backtest"}
                onClick={() => setActiveTab("backtest")}
                as="button"
              />
              <TopNavItem
                label="Alerts"
                isSelected={activeTab === "alerts"}
                onClick={() => setActiveTab("alerts")}
                as="button"
              />
              <TopNavItem
                label="Study"
                isSelected={activeTab === "study"}
                onClick={() => setActiveTab("study")}
                as="button"
              />
              <TopNavItem
                label="Cleanup"
                isSelected={activeTab === "cleanup"}
                onClick={() => setActiveTab("cleanup")}
                as="button"
              />
            </HStack>
          }
          endContent={
            <HStack align="center" gap={3}>
              {/* Project Selector */}
              <HStack align="center" gap={1}>
                <Text type="supporting" weight="medium">
                  Project:
                </Text>
                {projects.length > 0 ? (
                  <Selector
                    label="Active Project"
                    isLabelHidden
                    size="sm"
                    options={projectOptions}
                    value={selectedProject?.id || ""}
                    onChange={(val) => {
                      const match = projects.find((p) => p.id === val);
                      if (match) setSelectedProject(match);
                    }}
                    width={180}
                  />
                ) : (
                  <Text type="supporting">None</Text>
                )}
                <Button
                  label="+"
                  variant="secondary"
                  size="sm"
                  onClick={() => setIsNewProjectOpen(true)}
                  tooltip="Create new project"
                />
              </HStack>

              {/* Engine Status */}
              <HStack align="center" gap={1}>
                <StatusDot
                  variant={engineConnected ? "success" : "error"}
                  label={statusText}
                />
                <Text type="supporting">
                  {statusText}
                </Text>
              </HStack>
            </HStack>
          }
        />
      }
    >
      {/* Domain View Switcher */}
      {activeTab === "data" && <DataView />}
      {activeTab === "research" && (
        <ResearchView project={selectedProject} focusSecurityId={focusSecurityId} />
      )}
      {activeTab === "valuation" && <ValuationView project={selectedProject} />}
      {activeTab === "models" && <ModelsView project={selectedProject} />}
      {activeTab === "backtest" && <BacktestView project={selectedProject} />}
      {activeTab === "alerts" && (
        <AlertsView
          project={selectedProject}
          engineConnected={engineConnected}
          onOpenSecurity={openSecurity}
        />
      )}
      {activeTab === "study" && <StudyView project={selectedProject} />}
      {activeTab === "cleanup" && (
        <CleanupView project={selectedProject} onProjectDeleted={handleProjectDeleted} />
      )}


      {/* New Project Dialog */}
      <Dialog
        isOpen={isNewProjectOpen}
        onOpenChange={(open) => {
          if (!open) setIsNewProjectOpen(false);
        }}
      >
        <DialogHeader
          title="Create New Project"
          subtitle="Group research theses, valuation revisions, models, and backtest runs."
        />
        <form onSubmit={handleCreateProject}>
          <VStack gap={4}>
            {projectError && (
              <Banner status="error" title="Creation Error">
                {projectError}
              </Banner>
            )}

            <VStack gap={1}>
              <TextInput
                label="Project Name"
                value={newProjectName}
                onChange={(val) => setNewProjectName(String(val ?? ""))}
                placeholder="e.g. US Tech & Semiconductors"
                isRequired
                hasAutoFocus
              />
            </VStack>

            <HStack justify="end" gap={2}>
              <Button
                label="Cancel"
                variant="secondary"
                onClick={() => setIsNewProjectOpen(false)}
                type="button"
                isDisabled={isCreatingProject}
              />
              <Button label="Create Project" variant="primary" type="submit" isLoading={isCreatingProject} />
            </HStack>
          </VStack>
        </form>
      </Dialog>
    </AppShell>
  );
}
