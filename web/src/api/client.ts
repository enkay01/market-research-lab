import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Project = components["schemas"]["ProjectResponse"];
export type ProjectCreate = components["schemas"]["ProjectCreateRequest"];
export type DefinitionCreate = components["schemas"]["DefinitionCreateRequest"];
export type CoverageResponse = components["schemas"]["CoverageResponse"];
export type CorporateActionResponse = components["schemas"]["CorporateActionResponse"];
export type DailyBarResponse = components["schemas"]["DailyBarResponse"];
export type FundamentalFactResponse = components["schemas"]["FundamentalFactResponse"];
export type ProviderDownloadRequest =
  | components["schemas"]["TiingoDownloadRequest"]
  | components["schemas"]["SecEdgarDownloadRequest"];
export type ProviderDownloadResponse = components["schemas"]["ProviderDownloadResponse"];

export type Security = components["schemas"]["SecurityResponse"];
export type SecuritySummary = components["schemas"]["SecuritySummaryResponse"];
export type Watchlist = components["schemas"]["WatchlistResponse"];
export type WatchlistItem = components["schemas"]["WatchlistItemResponse"];
export type ResearchThesis = components["schemas"]["ResearchThesisResponse"];

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly errorBody?: unknown,
  ) {
    super(message);
  }
}

const client = createClient<paths>({ baseUrl: "" });

async function dataOrThrow<T>(request: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await request;
  if (data !== undefined) return data;
  let message = response.statusText || `Request failed with status ${response.status}`;
  if (typeof error === "object" && error !== null) {
    if ("message" in error && typeof (error as any).message === "string") {
      message = (error as any).message;
    } else if ("detail" in error) {
      const detail = (error as any).detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail)) {
        message = detail.map((d: any) => (typeof d === "object" && d?.msg ? d.msg : JSON.stringify(d))).join("; ");
      }
    }
  }
  throw new ApiError(response.status, message, error);
}

export const api = {
  health: () => dataOrThrow(client.GET("/api/health")),
  listProjects: () => dataOrThrow(client.GET("/api/projects")),
  createProject: (project: ProjectCreate) => dataOrThrow(client.POST("/api/projects", { body: project })),
  saveDefinition: (projectId: string, definition: DefinitionCreate) =>
    dataOrThrow(
      client.POST("/api/projects/{project_id}/definitions", {
        params: { path: { project_id: projectId } },
        body: definition,
      }),
    ),
  renameProject: (projectId: string, request: { name: string }) =>
    dataOrThrow(
      client.PATCH("/api/projects/{project_id}", {
        params: { path: { project_id: projectId } },
        body: request,
      }),
    ),
  deleteProject: (projectId: string) =>
    dataOrThrow(
      client.DELETE("/api/projects/{project_id}", {
        params: { path: { project_id: projectId } },
      }),
    ),
  importDataset: (source: string, file: File) => {
    const formData = new FormData();
    formData.append("source", source);
    formData.append("file", file);
    return dataOrThrow(
      client.POST("/api/datasets", {
        body: formData as unknown as components["schemas"]["Body_import_dataset_api_datasets_post"],
        bodySerializer: (body) => body as unknown as FormData,
      }),
    );
  },
  downloadDataset: (request: ProviderDownloadRequest) =>
    dataOrThrow(
      client.POST("/api/datasets/download", {
        body: request,
      }),
    ),
  getCoverage: (datasetVersionId: string) =>
    dataOrThrow(
      client.GET("/api/datasets/{dataset_version_id}/coverage", {
        params: { path: { dataset_version_id: datasetVersionId } },
      }),
    ),
  listDatasets: () => dataOrThrow(client.GET("/api/datasets")),
  getPreview: (datasetVersionId: string) =>
    dataOrThrow(
      client.GET("/api/datasets/{dataset_version_id}/preview", {
        params: { path: { dataset_version_id: datasetVersionId } },
      }),
    ) as Promise<Record<string, unknown>[]>,
  getHistory: (datasetVersionId: string, params?: { as_of?: string; symbol?: string }) =>
    dataOrThrow(
      client.GET("/api/datasets/{dataset_version_id}/history", {
        params: {
          path: { dataset_version_id: datasetVersionId },
          query: params,
        },
      }),
    ),
  getFundamentals: (datasetVersionId: string, params?: { as_of?: string; symbol?: string }) =>
    dataOrThrow(
      client.GET("/api/datasets/{dataset_version_id}/fundamentals", {
        params: {
          path: { dataset_version_id: datasetVersionId },
          query: params,
        },
      }),
    ),
  getCorporateActions: (datasetVersionId: string, params?: { as_of?: string; symbol?: string }) =>
    dataOrThrow(
      client.GET("/api/datasets/{dataset_version_id}/corporate-actions", {
        params: {
          path: { dataset_version_id: datasetVersionId },
          query: params,
        },
      }),
    ),
  listSecurities: (params?: { query?: string; limit?: number }) =>
    dataOrThrow(
      client.GET("/api/securities", {
        params: { query: params },
      }),
    ),
  getSecurityDetails: (securityId: string, params?: { project_id?: string }) =>
    dataOrThrow(
      client.GET("/api/securities/{security_id}", {
        params: {
          path: { security_id: securityId },
          query: params,
        },
      }),
    ),
  getWatchlist: (
    projectId: string,
    params?: {
      query?: string;
      exchange?: string;
      thesis_status?: string;
      sort_by?: string;
      sort_order?: string;
      offset?: number;
      limit?: number;
    },
  ) =>
    dataOrThrow(
      client.GET("/api/projects/{project_id}/watchlist", {
        params: {
          path: { project_id: projectId },
          query: params,
        },
      }),
    ),
  addToWatchlist: (projectId: string, request: { identifier: string }) =>
    dataOrThrow(
      client.POST("/api/projects/{project_id}/watchlist", {
        params: { path: { project_id: projectId } },
        body: request,
      }),
    ),
  removeFromWatchlist: (projectId: string, securityId: string) =>
    dataOrThrow(
      client.DELETE("/api/projects/{project_id}/watchlist/{security_id}", {
        params: {
          path: { project_id: projectId, security_id: securityId },
        },
      }),
    ),
  getThesis: (projectId: string, securityId: string) =>
    dataOrThrow(
      client.GET("/api/projects/{project_id}/research/{security_id}", {
        params: {
          path: { project_id: projectId, security_id: securityId },
        },
      }),
    ),
  saveThesis: (projectId: string, securityId: string, request: { content: string }) =>
    dataOrThrow(
      client.PUT("/api/projects/{project_id}/research/{security_id}", {
        params: {
          path: { project_id: projectId, security_id: securityId },
        },
        body: request,
      }),
    ),
};
