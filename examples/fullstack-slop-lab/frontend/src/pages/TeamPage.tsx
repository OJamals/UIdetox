import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { Spinner } from "../components/Spinner";
import { Toast } from "../components/Toast";
import type { TeamMember } from "../types";

export function TeamPage() {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const loadTeam = useCallback(async () => {
    try {
      setMembers(await api.getTeam());
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Team roster could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTeam();
  }, [loadTeam]);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      await api.inviteTeamMember(String(data.get("email")), String(data.get("role")));
      setShowInvite(false);
      setToast("Invitation sent.");
      await loadTeam();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Invitation could not be sent.");
    }
  }

  async function remove(memberId: number) {
    try {
      setError("");
      await api.removeTeamMember(memberId);
      setToast("Team member removed.");
      await loadTeam();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Team member could not be removed.");
    }
  }

  if (loading) return <Spinner />;

  return (
    <div className="page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">Access roster</span>
          <h1>Team</h1>
          <p>Inspect workspace roles and manage invitations in the synthetic tenant.</p>
        </div>
        <button type="button" className="primary-button" onClick={() => setShowInvite(true)}>
          Invite member
        </button>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <div className="team-grid">
        {members.map((member) => (
          <article className="team-card" key={member.id}>
            <div aria-hidden="true" className="avatar-xl">{member.avatar}</div>
            <h2>{member.name}</h2>
            <p>{member.role}</p>
            <a href={`mailto:${member.email}`}>{member.email}</a>
            <p className={member.online ? "positive" : ""}>{member.online ? "Online" : "Offline"}</p>
            <button type="button" className="secondary-button" onClick={() => void remove(member.id)}>
              Remove member
            </button>
          </article>
        ))}
      </div>

      {showInvite ? (
        <dialog aria-labelledby="invite-member-title" className="modal-card create-form" open>
          <form onSubmit={invite}>
            <h2 id="invite-member-title">Invite team member</h2>
            <p>The backend records this invitation as a synthetic roster entry.</p>
            <label htmlFor="invite-email">Email address</label>
            <input id="invite-email" autoComplete="email" name="email" type="email" required />
            <label htmlFor="invite-role">Workspace role</label>
            <select id="invite-role" name="role" defaultValue="Viewer">
              <option>Viewer</option>
              <option>Developer</option>
              <option>Designer</option>
              <option>Admin</option>
            </select>
            <div className="modal-actions">
              <button type="button" className="secondary-button" onClick={() => setShowInvite(false)}>
                Cancel
              </button>
              <button type="submit" className="primary-button">Send invitation</button>
            </div>
          </form>
        </dialog>
      ) : null}

      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
    </div>
  );
}
