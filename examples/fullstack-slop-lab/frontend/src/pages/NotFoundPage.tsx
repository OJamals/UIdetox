import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="not-found glass-card">
      <span>🪐</span>
      <h1>Oops! You found the void...</h1>
      <p>This magical page doesn't exist yet.</p>
      <Link className="primary-button" to="/">
        Take me home
      </Link>
    </section>
  );
}

