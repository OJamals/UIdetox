import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";
import { MagicCard } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import { Toast } from "../components/Toast";
import type { TeamMember } from "../types";

export function TeamPage() {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const load = () =>
    api
      .getTeam()
      .then(setMembers)
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  const invite = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await api.inviteTeamMember(String(data.get("email")), String(data.get("role")));
    setShowInvite(false);
    setToast("Invitation sent successfully!");
    await load();
  };

  const remove = async (memberId: number) => {
    setError("");
    try {
      await api.removeTeamMember(memberId);
      setToast("Team member removed!");
      await load();
    } catch {
      setError("Oops! Something went wrong...");
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">TEAM COLLABORATION</span>
          <h1>Your dream team</h1>
          <p>Empower everyone to do their best work together.</p>
        </div>
        <button className="primary-button" onClick={() => setShowInvite(true)}>
          + Invite team member
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="team-grid">
        {members.map((member) => (
          <article className="team-card glass-card" key={member.id}>
            <button className="tiny-button team-menu">•••</button>
            <div className="avatar-xl">
              {member.avatar}
              <i className={member.online ? "online" : ""} />
            </div>
            <h2>{member.name}</h2>
            <p>{member.role}</p>
            <small>{member.email}</small>
            <div className="skill-pills">
              <span>Creative</span>
              <span>AI Expert</span>
              <span>Leader</span>
            </div>
            <button className="secondary-button full" onClick={() => remove(member.id)}>
              Remove member
            </button>
          </article>
        ))}
      </div>

      {showInvite && (
        <div className="modal-backdrop">
          <form className="modal-card create-form glass-card" onSubmit={invite}>
            <div className="icon-tile">👥</div>
            <h2>Grow your amazing team</h2>
            <p>Invite someone to collaborate and create magic together.</p>
            <input name="email" type="email" placeholder="Enter email address..." required />
            <select name="role" defaultValue="Viewer">
              <option>Viewer</option>
              <option>Developer</option>
              <option>Designer</option>
              <option>Admin</option>
            </select>
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setShowInvite(false)}
              >
                Maybe later
              </button>
              <button className="primary-button">Send magical invite</button>
            </div>
          </form>
        </div>
      )}

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
