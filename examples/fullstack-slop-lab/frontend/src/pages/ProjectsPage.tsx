import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { ConfirmModal } from "../components/ConfirmModal";
import { OperationalSection } from "../components/MagicCard";
import { ModalDialog } from "../components/ModalDialog";
import { ProjectTable } from "../components/ProjectTable";
import { Spinner } from "../components/Spinner";
import { Toast } from "../components/Toast";
import type { Project } from "../types";

export function ProjectsPage() {
  const [searchParams] = useSearchParams();
  const searchQuery = searchParams.get("search") || "";
  const [projects, setProjects] = useState<Project[]>([]);
  const [search, setSearch] = useState(searchQuery);
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("name");
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");

  const loadProjects = useCallback(async () => {
    try {
      setError("");
      setProjects(await api.getProjects());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Projects could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    setSearch(searchQuery);
  }, [searchQuery]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return projects
      .filter((project) => status === "all" || project.status === status)
      .filter((project) => `${project.name} ${project.description}`.toLowerCase().includes(query))
      .sort((left, right) =>
        sort === "budget"
          ? right.budget - left.budget
          : left.name.localeCompare(right.name),
      );
  }, [projects, search, sort, status]);

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      setError("");
      await api.createProject({
        name: String(data.get("name")),
        description: String(data.get("description")),
        status: "planning",
        progress: 0,
        budget: Number(data.get("budget")),
        owner_name: "Northstar Operator",
        tags: ["new"],
      });
      setShowCreate(false);
      setToast("Project created.");
      await loadProjects();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Project creation failed.");
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    try {
      setError("");
      await api.deleteProject(deleting.id);
      setDeleting(null);
      setToast("Project deleted.");
      await loadProjects();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Project deletion failed.");
    }
  }

  if (loading) return <Spinner />;

  return (
    <div className="page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">Portfolio register</span>
          <h1>Projects</h1>
          <p>Review ownership, delivery progress, and budget from one auditable list.</p>
        </div>
        <button type="button" className="primary-button" onClick={() => setShowCreate(true)}>
          Create project
        </button>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <OperationalSection>
        <div className="toolbar">
          <label>
            Search projects
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Name or description"
            />
          </label>
          <label>
            Status
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="all">All statuses</option>
              <option value="planning">Planning</option>
              <option value="active">Active</option>
              <option value="completed">Completed</option>
            </select>
          </label>
          <label>
            Sort by
            <select value={sort} onChange={(event) => setSort(event.target.value)}>
              <option value="name">Name</option>
              <option value="budget">Budget, high to low</option>
            </select>
          </label>
        </div>
        <ProjectTable projects={filtered} onDelete={setDeleting} />
      </OperationalSection>

      <ModalDialog
        open={showCreate}
        labelledBy="create-project-title"
        className="create-form"
        onClose={() => setShowCreate(false)}
      >
          <form onSubmit={createProject}>
            <h2 id="create-project-title">Create project</h2>
            <p>New projects begin in planning with no recorded progress.</p>
            <label htmlFor="project-name">Project name</label>
            <input id="project-name" name="name" type="text" required />
            <label htmlFor="project-description">Description</label>
            <textarea id="project-description" name="description" required />
            <label htmlFor="project-budget">Budget</label>
            <input id="project-budget" min="0" name="budget" type="number" required />
            <div className="modal-actions">
              <button type="button" className="secondary-button" onClick={() => setShowCreate(false)}>
                Cancel
              </button>
              <button type="submit" className="primary-button">Create project</button>
            </div>
          </form>
      </ModalDialog>

      <ConfirmModal
        open={Boolean(deleting)}
        title="Delete project?"
        message="This removes the project from the synthetic fixture database."
        onConfirm={confirmDelete}
        onClose={() => setDeleting(null)}
      />
      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
    </div>
  );
}
