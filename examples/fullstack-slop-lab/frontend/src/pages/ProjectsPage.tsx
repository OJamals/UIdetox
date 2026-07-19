import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { ConfirmModal } from "../components/ConfirmModal";
import { MagicCard } from "../components/MagicCard";
import { ProjectTable } from "../components/ProjectTable";
import { Spinner } from "../components/Spinner";
import { Toast } from "../components/Toast";
import type { Project } from "../types";

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [toast, setToast] = useState("");

  const load = () =>
    api
      .getProjects()
      .then(setProjects)
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(
    () =>
      projects.filter((project) =>
        `${project.name} ${project.description}`.toLowerCase().includes(search.toLowerCase()),
      ),
    [projects, search],
  );

  const createProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await api.createProject({
      name: String(data.get("name")),
      description: String(data.get("description")),
      status: "planning",
      progress: 0,
      budget: Number(data.get("budget")),
      owner_name: "Jane Doe",
      tags: ["new", "ai"],
    });
    setShowCreate(false);
    setToast("Your magical new project was created!");
    await load();
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    await api.deleteProject(deleting.id);
    setDeleting(null);
    setToast("Project successfully deleted!");
    await load();
  };

  if (loading) return <Spinner />;

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">PROJECT MANAGEMENT</span>
          <h1>Projects</h1>
          <p>Seamlessly manage every initiative in one beautiful place.</p>
        </div>
        <button className="primary-button" onClick={() => setShowCreate(true)}>
          + Create new project
        </button>
      </div>

      <MagicCard>
        <div className="toolbar">
          <div className="search-box large">
            <span>🔍</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search projects..."
            />
          </div>
          <button className="pill-button">All statuses⌄</button>
          <button className="pill-button">Sort: Newest⌄</button>
          <button className="icon-button">⚙️</button>
        </div>
        <ProjectTable projects={filtered} onDelete={setDeleting} />
      </MagicCard>

      {showCreate && (
        <div className="modal-backdrop">
          <form className="modal-card create-form glass-card" onSubmit={createProject}>
            <div className="icon-tile">🚀</div>
            <h2>Create something amazing</h2>
            <p>Enter your details below to unlock limitless possibilities.</p>
            <input name="name" placeholder="Project name" required />
            <textarea name="description" placeholder="Describe your vision..." />
            <input name="budget" type="number" placeholder="Budget" />
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setShowCreate(false)}
              >
                Cancel
              </button>
              <button className="primary-button">Create project</button>
            </div>
          </form>
        </div>
      )}

      <ConfirmModal
        open={Boolean(deleting)}
        title="Are you absolutely sure?"
        message="This action cannot be undone and your project will disappear forever."
        onConfirm={confirmDelete}
        onClose={() => setDeleting(null)}
      />
      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
