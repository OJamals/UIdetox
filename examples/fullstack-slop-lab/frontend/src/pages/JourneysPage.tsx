import { useEffect, useState } from "react";
import { api } from "../api/client";
import { JourneyStep } from "../components/JourneyStep";
import { Spinner } from "../components/Spinner";
import type { CustomerJourney } from "../types";

export function JourneysPage() {
  const [journeys, setJourneys] = useState<CustomerJourney[]>([]);
  const [selected, setSelected] = useState<CustomerJourney | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("Journey state is synchronized with the fixture API.");

  useEffect(() => {
    api.getJourneys().then((results) => {
      setJourneys(results);
      setSelected(results[0] || null);
    }).catch((reason) => {
      setNotice(reason instanceof Error ? reason.message : "Journeys could not be loaded.");
    }).finally(() => setLoading(false));
  }, []);

  async function activate() {
    if (!selected) return;
    try {
      const saved = await api.activateJourney(selected.id);
      setJourneys((current) => current.map((journey) => journey.id === saved.id ? saved : journey));
      setSelected(saved);
      setNotice(`${saved.name} published.`);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "Journey could not be published.");
    }
  }

  if (loading) return <Spinner label="Loading journeys…" />;

  const steps = selected ? [
    { title: "Entry trigger", detail: selected.entryTrigger, status: "Listening" },
    { title: "Audience evaluation", detail: selected.audienceSegments.join(", "), status: "Mapped" },
    { title: "Configured actions", detail: `${selected.stepCount} persisted steps`, status: selected.active ? "Active" : "Draft" },
  ] : [];

  return (
    <div className="fixture-page journeys-page">
      <header className="page-heading"><div><span className="eyebrow">Lifecycle orchestration</span><h1>Journeys</h1><p>Inspect entry conditions, audience segments, and publication state.</p></div></header>
      <p className="status-ribbon" role="status">{notice}</p>
      <div className="journey-workspace">
        <nav aria-label="Customer journeys" className="journey-library">
          <h2>Journey library</h2>
          {journeys.map((journey) => (
            <button type="button" className={`journey-library-item ${selected?.id === journey.id ? "selected" : ""}`} key={journey.id} onClick={() => setSelected(journey)}>
              <span aria-hidden="true" className={journey.active ? "active-dot" : "draft-dot"} />
              <span><strong>{journey.name}</strong><small>{journey.entryTrigger}</small></span>
              <b>{journey.stepCount}</b>
            </button>
          ))}
        </nav>
        <section className="journey-canvas" aria-labelledby="journey-title">
          <header className="journey-canvas-toolbar">
            <div><h2 id="journey-title">{selected?.name || "No journey selected"}</h2><p>Owner: {selected?.owner.name || "Not available"}</p></div>
            {selected && !selected.active ? <button type="button" onClick={() => void activate()}>Publish journey</button> : <span className="status-pill">{selected?.active ? "Published" : "Select a journey"}</span>}
          </header>
          <div className="journey-flow">
            {steps.map((step, index) => <JourneyStep key={step.title} number={index + 1} title={step.title} detail={step.detail} status={step.status} />)}
          </div>
        </section>
      </div>
    </div>
  );
}
