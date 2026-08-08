import { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import { api, type Project } from "./api/client";
import "./styles.css";

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Project>();
  const [name, setName] = useState("");
  const [status, setStatus] = useState("Connecting to the local engine…");

  useEffect(() => {
    void Promise.all([api.health(), api.listProjects()])
      .then(([health, availableProjects]) => {
        setProjects(availableProjects);
        setSelected(availableProjects[0]);
        setStatus(health.status === "ok" ? "Local engine connected" : "Engine is unavailable");
      })
      .catch((error: unknown) => setStatus(error instanceof Error ? error.message : "Unable to connect"));
  }, []);

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const project = await api.createProject({ name });
    setProjects((current) => [project, ...current]);
    setSelected(project);
    setName("");
  }

  async function saveStarterRevision() {
    if (!selected) return;
    const saved = await api.saveDefinition(selected.id, {
      kind: "valuation",
      name: "First valuation",
      definition: { method: "fcff_dcf", currency: "USD" },
    });
    setStatus(`Saved ${saved.revision} for ${selected.name}`);
  }

  async function renameProject() {
    if (!selected) return;
    const newName = prompt("New project name:", selected.name);
    if (!newName || newName.trim() === "" || newName === selected.name) return;
    try {
      const updated = await api.renameProject(selected.id, { name: newName });
      setProjects((current) => current.map((p) => (p.id === updated.id ? updated : p)));
      setSelected(updated);
      setStatus(`Renamed project to ${updated.name}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to rename project");
    }
  }

  async function deleteProject() {
    if (!selected) return;
    if (!confirm(`Are you sure you want to delete project "${selected.name}"?`)) return;
    try {
      await api.deleteProject(selected.id);
      setProjects((current) => {
        const remaining = current.filter((p) => p.id !== selected.id);
        setSelected(remaining.length > 0 ? remaining[0] : undefined);
        return remaining;
      });
      setStatus(`Deleted project ${selected.name}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to delete project");
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">LOCAL WORKSPACE</p>
        <div>
          <h1>Market Research Lab</h1>
          <p className="subtle">Turn market ideas into explicit, reproducible research.</p>
        </div>
        <span className="status">{status}</span>
      </header>
      <section className="panel">
        <div>
          <p className="eyebrow">PROJECTS</p>
          <h2>Start with a research workspace</h2>
          <p>Create a local Project; its files stay on this machine.</p>
        </div>
        <form onSubmit={createProject}>
          <label htmlFor="project-name">Project name</label>
          <div className="form-row">
            <input id="project-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Quality compounders" required />
            <button type="submit">Create Project</button>
          </div>
        </form>
      </section>
      <section className="workspace">
        <nav aria-label="Projects">
          <p className="eyebrow">YOUR PROJECTS</p>
          {projects.length ? projects.map((project) => (
            <button className={project.id === selected?.id ? "project active" : "project"} key={project.id} onClick={() => setSelected(project)}>{project.name}</button>
          )) : <p className="empty">No Projects yet.</p>}
        </nav>
        <article>
          {selected ? <>
            <p className="eyebrow">{selected.name.toUpperCase()}</p>
            <h2>Project ready</h2>
            <p>Research, data coverage, Valuations, Indicators, Backtests, and Alerts will grow here in the next Epics.</p>
            <div className="form-row" style={{ marginTop: '1rem', gap: '0.5rem' }}>
              <button className="secondary" onClick={() => void saveStarterRevision()}>Save a starter Valuation revision</button>
              <button className="secondary" onClick={() => void renameProject()}>Rename Project</button>
              <button className="secondary" onClick={() => void deleteProject()} style={{ color: 'var(--color-danger-fg)' }}>Delete Project</button>
            </div>
          </> : <>
            <p className="eyebrow">READY WHEN YOU ARE</p>
            <h2>Create your first Project</h2>
            <p>Its research and future Run artifacts will be stored locally and can be reopened after a restart.</p>
          </>}
        </article>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
