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
import { CreateStrategyView } from "./views/CreateStrategyView";
import { BacktestView } from "./views/BacktestView";

export type DomainTab = "datasets" | "strategies" | "backtest";

function isDomainTab(value: string | null): value is DomainTab {
  return value !== null && ["datasets", "strategies", "backtest"].includes(value);
}

export function App() {
  const [activeTab, setActiveTab] = useState<DomainTab>(() => {
    const params = new URLSearchParams(window.location.search);
    const tabParam = params.get("tab");
    if (isDomainTab(tabParam)) {
      return tabParam;
    }
    if (params.get("variant")) {
      return "backtest";
    }
    return "datasets";
  });
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | undefined>();
  const [engineConnected, setEngineConnected] = useState(false);
  const [statusText, setStatusText] = useState("Connecting…");

  // Project Creation Modal
  const [isNewProjectOpen, setIsNewProjectOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    async function checkHealthAndLoad() {
      try {
        const [health, availableProjects] = await Promise.all([api.health(), api.listProjects()]);
        if (!isMounted) return;
        setProjects(availableProjects);
        setSelectedProject((prev) => prev ?? availableProjects[0]);
        const isOk = health.status === "ok";
        setEngineConnected(isOk);
        setStatusText(isOk ? "Engine Online" : "Engine Unavailable");
      } catch (cause: unknown) {
        if (!isMounted) return;
        setEngineConnected(false);
        setStatusText(cause instanceof Error ? cause.message : "Engine Offline");
      }
    }

    void checkHealthAndLoad();
    const interval = setInterval(() => {
      void checkHealthAndLoad();
    }, 4000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
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
                label="1. Download Dataset"
                isSelected={activeTab === "datasets"}
                onClick={() => setActiveTab("datasets")}
                as="button"
              />
              <TopNavItem
                label="2. Create Strategy"
                isSelected={activeTab === "strategies"}
                onClick={() => setActiveTab("strategies")}
                as="button"
              />
              <TopNavItem
                label="3. Test Strategy & View Results"
                isSelected={activeTab === "backtest"}
                onClick={() => setActiveTab("backtest")}
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
      {/* 3 Core Views */}
      {activeTab === "datasets" && <DataView />}
      {activeTab === "strategies" && <CreateStrategyView project={selectedProject} />}
      {activeTab === "backtest" && <BacktestView project={selectedProject} />}
      {/* New Project Dialog */}
      <Dialog
        isOpen={isNewProjectOpen}
        onOpenChange={(open) => {
          if (!open) setIsNewProjectOpen(false);
        }}
      >
        <DialogHeader
          title="Create New Project"
          subtitle="Group custom strategy revisions and backtest execution runs."
        />
        <form onSubmit={handleCreateProject}>
          <VStack gap={4}>
            {projectError && (
              <Banner status="error" title="Creation Error" description={projectError} />
            )}

            <VStack gap={1}>
              <TextInput
                label="Project Name"
                value={newProjectName}
                onChange={(val) => setNewProjectName(String(val ?? ""))}
                placeholder="e.g. SPY Credit Spreads & Momentum"
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
