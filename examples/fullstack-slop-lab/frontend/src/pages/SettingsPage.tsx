import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";
import { MagicCard } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import { Toast } from "../components/Toast";
import type { WorkspaceSettings } from "../types";

export function SettingsPage() {
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [toast, setToast] = useState("");

  useEffect(() => {
    api.getSettings().then(setSettings);
  }, []);

  if (!settings) return <Spinner />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const saved = await api.saveSettings(settings);
    setSettings(saved);
    setToast("Settings saved successfully!");
  };

  return (
    <div className="page settings-page">
      <div className="page-heading centered">
        <div>
          <span className="eyebrow">PERSONALIZATION</span>
          <h1>Make it yours</h1>
          <p>Customize every detail to unlock your perfect workflow.</p>
        </div>
      </div>

      <form onSubmit={submit}>
        <MagicCard eyebrow="01 / GENERAL" title="Workspace settings">
          <div className="settings-form">
            <input
              value={settings.workspace_name}
              onChange={(event) =>
                setSettings({ ...settings, workspace_name: event.target.value })
              }
              placeholder="Workspace name"
            />
            <select
              value={settings.default_view}
              onChange={(event) =>
                setSettings({ ...settings, default_view: event.target.value })
              }
            >
              <option value="dashboard">Dashboard</option>
              <option value="projects">Projects</option>
              <option value="analytics">Analytics</option>
            </select>
          </div>
        </MagicCard>

        <MagicCard eyebrow="02 / PREFERENCES" title="Experience">
          <label className="toggle-row">
            <div>
              <b>Weekly inspiration digest</b>
              <small>Get magical ideas delivered every Friday.</small>
            </div>
            <input
              type="checkbox"
              checked={settings.weekly_digest}
              onChange={(event) =>
                setSettings({ ...settings, weekly_digest: event.target.checked })
              }
            />
            <span className="fake-toggle" />
          </label>
          <label className="toggle-row">
            <div>
              <b>Beautiful dark mode</b>
              <small>Transform your workspace into a stunning night experience.</small>
            </div>
            <input
              type="checkbox"
              checked={settings.dark_mode}
              onChange={(event) =>
                setSettings({ ...settings, dark_mode: event.target.checked })
              }
            />
            <span className="fake-toggle" />
          </label>
        </MagicCard>

        <MagicCard className="danger-zone" eyebrow="03 / DANGER" title="Danger zone">
          <div className="danger-row">
            <div>
              <b>Delete workspace</b>
              <p>Permanently remove everything. This cannot be undone.</p>
            </div>
            <button type="button" className="danger-button">
              Delete everything forever
            </button>
          </div>
        </MagicCard>

        <button className="primary-button save-settings">Save all changes</button>
      </form>

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}

