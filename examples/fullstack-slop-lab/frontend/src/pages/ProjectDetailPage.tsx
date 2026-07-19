import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ActivityFeed } from "../components/ActivityFeed";
import { MagicCard } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import { Toast } from "../components/Toast";
import type { Project } from "../types";

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [progress, setProgress] = useState(0);
  const [toast, setToast] = useState("");

  useEffect(() => {
    api.getProject(projectId).then((nextProject) => {
      setProject(nextProject);
      setProgress(nextProject.progress);
    });
  }, [projectId]);

  if (!project) return <Spinner label="Loading project magic..." />;

  const save = async () => {
    const updated = await api.updateProject(project.id, { progress });
    setProject(updated);
    setToast("Everything was saved successfully!");
  };

  return (
    <div className="page">
      <div className="breadcrumbs">
        <Link to="/projects">Projects</Link>
        <span>/</span>
        <span>{project.name}</span>
      </div>

      <section className="project-hero glass-card">
        <div className="icon-tile massive">🚀</div>
        <div>
          <span className={`status-pill ${project.status}`}>{project.status}</span>
          <h1>{project.name}</h1>
          <p>{project.description}</p>
          <div className="tag-row">
            {project.tags.map((tag) => (
              <span key={tag}>#{tag}</span>
            ))}
          </div>
        </div>
        <button className="primary-button">Share project</button>
      </section>

      <div className="three-column-grid">
        <MagicCard eyebrow="01 / OVERVIEW" title="Project details">
          <dl className="detail-list">
            <div>
              <dt>Owner</dt>
              <dd>{project.owner_name}</dd>
            </div>
            <div>
              <dt>Due date</dt>
              <dd>{project.due_date || "No date"}</dd>
            </div>
            <div>
              <dt>Budget</dt>
              <dd>${project.budget.toLocaleString()}</dd>
            </div>
          </dl>
        </MagicCard>

        <MagicCard eyebrow="02 / PROGRESS" title="Completion">
          <div className="giant-percentage">{progress}%</div>
          <input
            type="range"
            min="0"
            max="100"
            value={progress}
            onChange={(event) => setProgress(Number(event.target.value))}
          />
          <button className="primary-button full" onClick={save}>
            Save changes
          </button>
        </MagicCard>

        <MagicCard eyebrow="03 / HEALTH" title="Project health">
          <div className="health-score">A+</div>
          <p className="muted-on-color">Everything looks magical and on track!</p>
          <button className="secondary-button full">View insights</button>
        </MagicCard>
      </div>

      <MagicCard eyebrow="04 / TIMELINE" title="Recent activity">
        <ActivityFeed items={project.activity || []} />
      </MagicCard>

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}

