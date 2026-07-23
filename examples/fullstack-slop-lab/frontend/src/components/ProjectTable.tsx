import { Link } from "react-router-dom";
import type { Project } from "../types";

type Props = {
  projects: Project[];
  onDelete: (project: Project) => void;
};

export function ProjectTable({ projects, onDelete }: Props) {
  if (projects.length === 0) {
    return <p className="empty-state">No projects match the current view.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="tabular-nums">
        <thead>
          <tr>
            <th scope="col">Project</th>
            <th scope="col">Status</th>
            <th scope="col">Progress</th>
            <th scope="col">Budget</th>
            <th scope="col">Owner</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <tr key={project.id}>
              <td>
                <Link to={`/projects/${project.id}`}>
                  <b>{project.name}</b>
                  <small>{project.description}</small>
                </Link>
              </td>
              <td>
                <span className={`status-pill ${project.status}`}>{project.status}</span>
              </td>
              <td>
                <div className="progress-row">
                  <div
                    aria-label={`${project.name} progress`}
                    aria-valuemax={100}
                    aria-valuemin={0}
                    aria-valuenow={project.progress}
                    className="progress-track"
                    role="progressbar"
                  >
                    <span style={{ width: `${project.progress}%` }} />
                  </div>
                  <small>{project.progress}%</small>
                </div>
              </td>
              <td>${project.budget.toLocaleString()}</td>
              <td>{project.owner_name}</td>
              <td>
                <button
                  aria-label={`Delete ${project.name}`}
                  type="button"
                  className="tiny-button danger"
                  onClick={() => onDelete(project)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
