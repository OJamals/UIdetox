import { Link } from "react-router-dom";
import type { Project } from "../types";

type Props = {
  projects: Project[];
  onDelete: (project: Project) => void;
};

export function ProjectTable({ projects, onDelete }: Props) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Project</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Budget</th>
            <th>Owner</th>
            <th>Actions</th>
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
                  <div className="progress-track">
                    <span style={{ width: `${project.progress}%` }} />
                  </div>
                  <small>{project.progress}%</small>
                </div>
              </td>
              <td>${project.budget.toLocaleString()}</td>
              <td>{project.owner_name}</td>
              <td>
                <button className="tiny-button">•••</button>
                <button className="tiny-button danger" onClick={() => onDelete(project)}>
                  🗑️
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
