import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Project = components["schemas"]["ProjectResponse"];
export type ProjectCreate = components["schemas"]["ProjectCreateRequest"];
export type DefinitionCreate = components["schemas"]["DefinitionCreateRequest"];
export type CoverageResponse = components["schemas"]["CoverageResponse"];

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

const client = createClient<paths>({ baseUrl: "" });

async function dataOrThrow<T>(request: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await request;
  if (data !== undefined) return data;
  const message =
    typeof error === "object" && error && "message" in error && typeof error.message === "string"
      ? error.message
      : response.statusText;
  throw new ApiError(response.status, message);
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
  importDataset: async (source: string, file: File) => {
    const formData = new FormData();
    formData.append("source", source);
    formData.append("file", file);
    const response = await fetch("/api/datasets", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new ApiError(response.status, "Failed to upload dataset");
    }
    return response.json() as Promise<components["schemas"]["DatasetImportResponse"]>;
  },
  getCoverage: (datasetVersionId: string) =>
    dataOrThrow(
      client.GET("/api/datasets/{dataset_version_id}/coverage", {
        params: { path: { dataset_version_id: datasetVersionId } },
      }),
    ),
};
