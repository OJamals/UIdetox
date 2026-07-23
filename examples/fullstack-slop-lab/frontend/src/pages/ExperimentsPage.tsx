import { useEffect, useState } from "react";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import type { Experiment } from "../types";

export function ExperimentsPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("Experiment state is loaded from the fixture API.");

  useEffect(() => {
    api.getExperiments()
      .then(setExperiments)
      .catch((reason) => setNotice(reason instanceof Error ? reason.message : "Experiments could not be loaded."))
      .finally(() => setLoading(false));
  }, []);

  async function toggle(experiment: Experiment) {
    try {
      const saved = await api.saveExperiment({ ...experiment, enabled: !experiment.enabled });
      setExperiments((current) => current.map((item) => item.key === saved.key ? saved : item));
      setNotice(`${saved.title} is now ${saved.enabled ? "enabled" : "disabled"}.`);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "Experiment state could not be saved.");
    }
  }

  if (loading) return <Spinner label="Loading experiments…" />;

  return (
    <div className="fixture-page experiments-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">Feature controls</span>
          <h1>Experiments</h1>
          <p>Review rollout audiences and persist enablement without optimistic local drift.</p>
        </div>
      </header>
      <p className="status-ribbon" role="status">{notice}</p>

      <div className="experiment-list">
        {experiments.map((experiment) => (
          <OperationalSection
            key={experiment.key}
            title={experiment.title}
            subtitle={experiment.description}
            badge={experiment.enabled ? "Enabled" : "Disabled"}
          >
            <div className="experiment-control-row">
              <label htmlFor={`experiment-${experiment.key}`}>
                Enabled
                <input
                  id={`experiment-${experiment.key}`}
                  type="checkbox"
                  checked={experiment.enabled}
                  onChange={() => void toggle(experiment)}
                />
              </label>
              <div>
                <span>Rollout</span>
                <output>{experiment.rolloutPercent}%</output>
                <progress max="100" value={experiment.rolloutPercent}>{experiment.rolloutPercent}%</progress>
              </div>
              <div className="audience-pills" aria-label="Audience segments">
                {experiment.audience.map((audience) => <span key={audience}>{audience}</span>)}
              </div>
            </div>
          </OperationalSection>
        ))}
      </div>
    </div>
  );
}
