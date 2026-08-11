import { FormEvent, useEffect, useState, useRef } from "react";
import { createRoot } from "react-dom/client";

import {
  api,
  ApiError,
  type CoverageResponse,
  type CorporateActionResponse,
  type DailyBarResponse,
  type FundamentalFactResponse,
  type Project,
  type ProviderDownloadRequest,
} from "./api/client";
import "./styles.css";

type PreviewRow = Record<string, unknown>;

function toPreviewRows(
  rows: Array<DailyBarResponse | CorporateActionResponse | FundamentalFactResponse>,
): PreviewRow[] {
  return rows.map((row) => ({ ...row }));
}

function isErrorBody(value: unknown): value is { code?: string; message?: string } {
  if (typeof value !== "object" || value === null) return false;
  if ("code" in value && typeof value.code !== "string") return false;
  return !("message" in value) || typeof value.message === "string";
}

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Project>();
  const [name, setName] = useState("");
  const [status, setStatus] = useState("Connecting to the local engine…");
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [importError, setImportError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [provider, setProvider] = useState<ProviderDownloadRequest["provider"]>("tiingo");
  const [providerSymbols, setProviderSymbols] = useState("");
  const [providerCiks, setProviderCiks] = useState("");
  const [providerStartDate, setProviderStartDate] = useState("");
  const [providerEndDate, setProviderEndDate] = useState("");
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadedVersionIds, setDownloadedVersionIds] = useState<string[]>([]);
  const [asOf, setAsOf] = useState("");
  const [pitError, setPitError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  async function handleImportDataset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const sourceInput = form.elements.namedItem("source") as HTMLInputElement;
    const fileInput = form.elements.namedItem("file") as HTMLInputElement;
    
    if (!fileInput.files || fileInput.files.length === 0) return;
    
    const source = sourceInput.value;
    const file = fileInput.files[0];
    
    setImportError(null);
    setPitError(null);
    setAsOf("");
    setIsUploading(true);
    setStatus(`Uploading dataset...`);
    try {
      const response = await api.importDataset(source, file);
      setStatus(`Imported dataset version`);
      
      const [newCoverage, rows] = await Promise.all([
        api.getCoverage(response.dataset_version_id),
        api.getPreview(response.dataset_version_id),
      ]);
      setCoverage(newCoverage);
      setPreviewRows(rows);
      
      sourceInput.value = "";
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unable to upload dataset";
      setImportError(msg);
      setStatus("Upload failed");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleProviderDownload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDownloadError(null);
    setPitError(null);
    setAsOf("");
    setIsDownloading(true);
    setStatus("Downloading " + (provider === "tiingo" ? "Tiingo prices" : "SEC EDGAR fundamentals") + "...");
    const request: ProviderDownloadRequest = {
      provider,
      symbols: provider === "tiingo" ? providerSymbols.split(",").map((value) => value.trim()).filter(Boolean) : [],
      ciks: provider === "sec_edgar" ? providerCiks.split(",").map((value) => value.trim()).filter(Boolean) : [],
      start_date: providerStartDate || null,
      end_date: providerEndDate || null,
    };
    try {
      const response = await api.downloadDataset(request);
      const [newCoverage, rows] = await Promise.all([
        api.getCoverage(response.dataset_version_id),
        api.getPreview(response.dataset_version_id),
      ]);
      setCoverage(newCoverage);
      setPreviewRows(rows);
      setDownloadedVersionIds(response.dataset_version_ids);
      setStatus("Downloaded " + response.dataset_version_ids.length + " Dataset Version" + (response.dataset_version_ids.length === 1 ? "" : "s"));
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Unable to download provider data";
      setDownloadError(msg);
      setStatus("Provider download failed");
    } finally {
      setIsDownloading(false);
    }
  }

  async function inspectDatasetVersion(datasetVersionId: string) {
    setDownloadError(null);
    try {
      const [newCoverage, rows] = await Promise.all([
        api.getCoverage(datasetVersionId),
        api.getPreview(datasetVersionId),
      ]);
      setCoverage(newCoverage);
      setPreviewRows(rows);
      setStatus("Inspecting Dataset Version " + datasetVersionId);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Unable to inspect Dataset Version");
    }
  }
  async function handlePitFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!coverage) return;
    setPitError(null);
    try {
      const isFundamentals = coverage?.is_fundamentals ?? false;
      const isCorporateActions = coverage?.is_corporate_actions ?? false;
      const params = { as_of: asOf.trim() || undefined };
      
      const fetchedRows = isFundamentals
        ? await api.getFundamentals(coverage.id, params)
        : isCorporateActions
          ? await api.getCorporateActions(coverage.id, params)
          : await api.getHistory(coverage.id, params);

      setPreviewRows(toPreviewRows(fetchedRows));
    } catch (error: unknown) {
      const errorBody =
        error instanceof ApiError && isErrorBody(error.errorBody) ? error.errorBody : null;
      const message = error instanceof ApiError && errorBody?.message ? String(errorBody.message) : (error instanceof Error ? error.message : "Point-in-time data required");

      const isPitError = 
        (error instanceof ApiError && (errorBody?.code === "point_in_time_data_required" || error.status === 400)) ||
        (error instanceof Error && error.message.includes("point_in_time_data_required")) ||
        (error instanceof Error && error.message.toLowerCase().includes("point-in-time"));

      if (isPitError) {
        setPitError(message);
        return;
      }

      if (errorBody?.code && errorBody?.message) {
        setPitError(`Error: ${errorBody.code} - ${errorBody.message}`);
        return;
      }
      const msg = error instanceof Error ? error.message : "Unable to filter history";
      setPitError(`Error: ${msg}`);
    }
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
            
            <div style={{ marginTop: '2rem' }}>
              <h3>Download Market Data</h3>
              <p className="subtle">Credentials stay in the local engine. They are never sent by the browser.</p>
              <form onSubmit={handleProviderDownload} style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem', marginBottom: '2rem' }}>
                <div>
                  <label htmlFor="provider">Provider</label>
                  <select id="provider" value={provider} onChange={(event) => setProvider(event.target.value as ProviderDownloadRequest["provider"])} style={{ width: '100%', padding: '12px 14px', border: '1px solid #bbc4b8', borderRadius: '5px' }}>
                    <option value="tiingo">Tiingo prices, splits, and dividends</option>
                    <option value="sec_edgar">SEC EDGAR fundamentals</option>
                  </select>
                </div>
                {provider === "tiingo" ? (
                  <div>
                    <label htmlFor="provider-symbols">Symbols</label>
                    <input id="provider-symbols" value={providerSymbols} onChange={(event) => setProviderSymbols(event.target.value)} placeholder="AAPL, MSFT" />
                  </div>
                ) : (
                  <div>
                    <label htmlFor="provider-ciks">SEC CIKs</label>
                    <input id="provider-ciks" value={providerCiks} onChange={(event) => setProviderCiks(event.target.value)} placeholder="320193, 789019" />
                  </div>
                )}
                <div className="form-row">
                  <div style={{ flex: 1 }}>
                    <label htmlFor="provider-start-date">Start date</label>
                    <input id="provider-start-date" type="date" value={providerStartDate} onChange={(event) => setProviderStartDate(event.target.value)} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label htmlFor="provider-end-date">End date</label>
                    <input id="provider-end-date" type="date" value={providerEndDate} onChange={(event) => setProviderEndDate(event.target.value)} />
                  </div>
                </div>
                <button type="submit" disabled={isDownloading} style={{ alignSelf: 'flex-start' }}>
                  {isDownloading ? "Downloading..." : "Download Data"}
                </button>
                {downloadError && (
                  <div style={{ padding: '0.75rem 1rem', backgroundColor: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--color-danger-fg, #ef4444)', borderRadius: '4px', color: 'var(--color-danger-fg, #ef4444)', fontSize: '0.9rem' }}>
                    <strong>Download Error:</strong> {downloadError}
                  </div>
                )}
              </form>
              {downloadedVersionIds.length > 1 && (
                <div style={{ marginBottom: '2rem' }}>
                  <strong>Dataset Versions created by this download:</strong>
                  <div className="form-row" style={{ flexWrap: 'wrap', marginTop: '0.5rem' }}>
                    {downloadedVersionIds.map((datasetVersionId) => (
                      <button key={datasetVersionId} type="button" className="secondary" onClick={() => void inspectDatasetVersion(datasetVersionId)}>
                        Inspect {datasetVersionId}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <h3>Import Market Data</h3>
              <form onSubmit={handleImportDataset} style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
                <div>
                  <label htmlFor="source">Source</label>
                  <input id="source" name="source" placeholder="e.g. Yahoo Finance" required style={{ width: '100%', marginTop: '0.25rem' }} />
                </div>
                <div>
                  <label htmlFor="file">Data File (CSV, JSON, Parquet)</label>
                  <input id="file" name="file" type="file" accept=".csv,.json,.parquet,.pq" ref={fileInputRef} required style={{ width: '100%', marginTop: '0.25rem' }} />
                </div>
                <button type="submit" disabled={isUploading} style={{ alignSelf: 'flex-start' }}>
                  {isUploading ? "Uploading..." : "Import Data"}
                </button>
                {importError && (
                  <div style={{ padding: '0.75rem 1rem', backgroundColor: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--color-danger-fg, #ef4444)', borderRadius: '4px', color: 'var(--color-danger-fg, #ef4444)', fontSize: '0.9rem' }}>
                    <strong>Upload Error:</strong> {importError}
                  </div>
                )}
              </form>
            </div>

            {coverage && (
              <div style={{ marginTop: '2rem', padding: '1rem', backgroundColor: 'var(--color-bg-secondary)', borderRadius: '4px' }}>
                <h3>Coverage Report</h3>
                <ul style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <li><strong>Source:</strong> {coverage.source}</li>
                  <li><strong>Coverage:</strong> {coverage.coverage_start || 'N/A'} to {coverage.coverage_end || 'N/A'}</li>
                  <li><strong>Rows Imported:</strong> {coverage.row_count}</li>
                  <li><strong>Rows Rejected:</strong> {coverage.rejected_count}</li>
                  <li><strong>Dataset Type:</strong> {coverage.dataset_type}</li>
                  <li>
                    <strong>Temporal Provenance:</strong>{" "}
                    {coverage.has_temporal_provenance ? (
                      <span style={{ color: "#22c55e", fontWeight: 600 }}>Present</span>
                    ) : (
                      <span style={{ color: "#ef4444", fontWeight: 600 }}>Lacking</span>
                    )}
                  </li>
                  <li><strong>Files Stored:</strong> {coverage.files.join(", ")}</li>
                  {coverage.missing_fields && Object.keys(coverage.missing_fields).length > 0 && (
                    <li><strong>Missing Fields:</strong> {Object.entries(coverage.missing_fields).map(([k, v]) => `${k}: ${v}`).join(", ")}</li>
                  )}
                </ul>
                {coverage.warnings.length > 0 && (
                  <div style={{ marginTop: '1rem' }}>
                    <strong>Warnings ({coverage.total_warnings ?? coverage.warnings.length}):</strong>
                    <ul style={{ color: 'var(--color-danger-fg)', fontSize: '0.9rem', marginTop: '0.5rem' }}>
                      {coverage.warnings.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  </div>
                )}

                <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--color-border)', paddingTop: '1rem' }}>
                  <h4>Point-in-Time Query (As-Of)</h4>
                  <form onSubmit={handlePitFilter} style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end', marginTop: '0.5rem' }}>
                    <div style={{ flex: 1 }}>
                      <label htmlFor="as-of-input" style={{ fontSize: '0.85rem', fontWeight: 500 }}>
                        As-Of Timestamp
                      </label>
                      <input
                        id="as-of-input"
                        type="text"
                        placeholder="e.g. 2023-01-01T16:00:00Z"
                        value={asOf}
                        onChange={(e) => setAsOf(e.target.value)}
                        style={{ width: '100%', marginTop: '0.25rem' }}
                      />
                    </div>
                    <button type="submit">Filter As-Of</button>
                  </form>
                  {pitError && (
                    <div
                      style={{
                        marginTop: '0.75rem',
                        padding: '0.75rem 1rem',
                        backgroundColor: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid var(--color-danger-fg, #ef4444)',
                        borderRadius: '4px',
                        color: 'var(--color-danger-fg, #ef4444)',
                        fontSize: '0.9rem',
                      }}
                    >
                      {pitError}
                    </div>
                  )}
                </div>

                {previewRows.length > 0 && (
                  <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--color-border)', paddingTop: '1rem' }}>
                    <h4>Data Preview (Top {previewRows.length} Rows)</h4>
                    <div style={{ overflowX: 'auto', marginTop: '0.5rem' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                        <thead>
                          <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                            {Object.keys(previewRows[0]).map((col) => (
                              <th key={col} style={{ padding: '0.5rem 0.75rem', fontWeight: 600 }}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {previewRows.map((row, idx) => (
                            <tr key={idx} style={{ borderBottom: '1px solid var(--color-border-subtle, #333)' }}>
                              {Object.keys(previewRows[0]).map((col) => (
                                <td key={col} style={{ padding: '0.4rem 0.75rem' }}>{String(row[col] ?? '')}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
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

