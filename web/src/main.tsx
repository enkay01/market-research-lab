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
            <button className="secondary" onClick={() => void saveStarterRevision()}>Save a starter Valuation revision</button>
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
