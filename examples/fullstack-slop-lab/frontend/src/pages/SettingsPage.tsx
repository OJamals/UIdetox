import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import { Toast } from "../components/Toast";
import type { WorkspaceSettings } from "../types";

export function SettingsPage() {
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.getSettings().then(setSettings).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "Workspace settings could not be loaded.");
    });
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    try {
      setError("");
      setSettings(await api.saveSettings(settings));
      setToast("Settings saved.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Workspace settings could not be saved.");
    }
  }

  if (!settings && !error) return <Spinner />;

  return (
    <div className="page settings-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">Workspace policy</span>
          <h1>Settings</h1>
          <p>Configure the supported preferences exposed by the workspace API.</p>
        </div>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}
      {settings ? (
        <form onSubmit={submit}>
          <OperationalSection eyebrow="01 / General" title="Workspace identity">
            <div className="settings-form">
              <label htmlFor="workspace-name">Workspace name</label>
              <input
                id="workspace-name"
                type="text"
                value={settings.workspace_name}
                onChange={(event) => setSettings({ ...settings, workspace_name: event.target.value })}
              />
              <label htmlFor="default-view">Default view</label>
              <select
                id="default-view"
                value={settings.default_view}
                onChange={(event) => {
                  const defaultView = event.target.value;
                  if (
                    defaultView === "dashboard" ||
                    defaultView === "projects" ||
                    defaultView === "analytics"
                  ) {
                    setSettings({ ...settings, default_view: defaultView });
                  }
                }}
              >
                <option value="dashboard">Dashboard</option>
                <option value="projects">Projects</option>
                <option value="analytics">Analytics</option>
              </select>
            </div>
          </OperationalSection>

          <OperationalSection eyebrow="02 / Preferences" title="Notifications and display">
            <label className="toggle-row" htmlFor="weekly-digest">
              <span><b>Weekly digest</b><small>Receive a Friday workspace summary.</small></span>
              <input
                id="weekly-digest"
                type="checkbox"
                checked={settings.weekly_digest}
                onChange={(event) => setSettings({ ...settings, weekly_digest: event.target.checked })}
              />
            </label>
            <label className="toggle-row" htmlFor="dark-mode">
              <span><b>Dark mode preference</b><small>Store the preference for compatible clients.</small></span>
              <input
                id="dark-mode"
                type="checkbox"
                checked={settings.dark_mode}
                onChange={(event) => setSettings({ ...settings, dark_mode: event.target.checked })}
              />
            </label>
          </OperationalSection>

          <aside className="boundary-note">
            Workspace deletion is intentionally absent: the fixture backend exposes no destructive workspace endpoint.
          </aside>
          <button type="submit" className="primary-button save-settings">Save settings</button>
        </form>
      ) : null}

      {toast ? <Toast message={toast} onClose={() => setToast("")} /> : null}
    </div>
  );
}
