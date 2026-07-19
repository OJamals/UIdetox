/*
 * Static operation manifest for UIdetox beta calibration.
 *
 * The runtime client intentionally hides transport behind a generic request()
 * wrapper. These uncalled probes provide literal fetch evidence for every
 * frontend contract so parity extraction can be tested independently from
 * wrapper inference. Never invoke this function in the application.
 */
export function semanticContractProbes(): Promise<Response>[] {
  return [
    fetch("/api/projects"),
    fetch("/api/projects", { method: "POST" }),
    fetch("/api/projects/{project_id}"),
    fetch("/api/projects/{project_id}", { method: "PATCH" }),
    fetch("/api/projects/{project_id}", { method: "DELETE" }),
    fetch("/api/metrics"),
    fetch("/api/activity"),
    fetch("/api/team"),
    fetch("/api/team/invite", { method: "POST" }),
    fetch("/api/team/{member_id}", { method: "DELETE" }),
    fetch("/api/settings"),
    fetch("/api/settings", { method: "PUT" }),
    fetch("/api/recommendations"),
  ];
}
