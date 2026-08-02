import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import { ActivityFeed } from "../components/ActivityFeed";
import { OperationalSection } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import { Toast } from "../components/Toast";
import type { Project } from "../types";

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [progress, setProgress] = useState(0);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");

  const loadProject = useCallback(async () => {
    setError("");
    setProject(null);
    try {
      const nextProject = await api.getProject(projectId);
      setProject(nextProject);
      setProgress(nextProject.progress);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Project could not be loaded.");
    }
  }, [projectId]);

  useEffect(() => {
    void loadProject();
  }, [loadProject]);

  async function save() {
    if (!project) return;
    try {
      await api.updateProject(project.id, { progress });
      const updated = await api.getProject(String(project.id));
      setProject(updated);
      setProgress(updated.progress);
      setToast("Project progress saved.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Project progress could not be saved.");
    }
  }

  if (!project && !error) return <Spinner label="Loading project…" />;
  if (!project) {
    return (
      <section className="error-banner project-error" role="alert">
        <h1>Project unavailable</h1>
        <p>We could not load the project record. Check the connection, then try again.</p>
        <div className="modal-actions">
          <button type="button" className="primary-button" onClick={() => void loadProject()}>Try again</button>
          <Link className="secondary-button" to="/projects">Back to projects</Link>
        </div>
      </section>
    );
  }

  const needsReview = project.status === "at-risk";
  let health = "Needs attention";
  let healthDetail = `Progress is ${progress}%. Confirm the next delivery checkpoint with the owner.`;
  if (needsReview) {
    health = "Needs review";
    healthDetail = `Progress is ${progress}%. Confirm the next delivery checkpoint with ${project.owner_name} before ${project.due_date || "the next review"}.`;
  } else if (progress >= 75) {
    health = "On track";
    healthDetail = `Progress is ${progress}%. Delivery remains on track.`;
  } else if (progress >= 40) {
    health = "Monitor";
  }

  return (
    <div className="page">
      <nav aria-label="Breadcrumb" className="breadcrumbs">
        <Link to="/projects">Projects</Link><span aria-hidden="true">/</span><span>{project.name}</span>
      </nav>

      <header className="project-hero">
        <div>
          <span className={`status-pill ${project.status}`}>{project.status}</span>
          <h1>{project.name}</h1>
          <p>{project.description}</p>
          <div className="tag-row">{project.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
        </div>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <div className="three-column-grid">
        <OperationalSection eyebrow="01 / Overview" title="Project details">
          <dl className="detail-list">
            <div><dt>Owner</dt><dd>{project.owner_name}</dd></div>
            <div><dt>Due date</dt><dd>{project.due_date || "Not scheduled"}</dd></div>
            <div><dt>Budget</dt><dd>${project.budget.toLocaleString()}</dd></div>
          </dl>
        </OperationalSection>

        <OperationalSection eyebrow="02 / Delivery" title="Completion">
          <output className="giant-percentage" htmlFor="project-progress">{progress}%</output>
          <label htmlFor="project-progress">Recorded project progress</label>
          <input
            id="project-progress"
            type="range"
            min="0"
            max="100"
            value={progress}
            onChange={(event) => setProgress(Number(event.target.value))}
          />
          <button type="button" className="primary-button full" onClick={() => void save()}>Save progress</button>
        </OperationalSection>

        <aside className="health-summary">
          <span className="eyebrow">03 / Health</span>
          <h2>{health}</h2>
          <p>{healthDetail}</p>
        </aside>
      </div>

      <OperationalSection eyebrow="04 / Timeline" title="Recent activity">
        <ActivityFeed items={project.activity || []} />
      </OperationalSection>

      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
    </div>
  );
}
