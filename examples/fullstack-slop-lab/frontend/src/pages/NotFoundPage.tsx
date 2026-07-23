import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="not-found glass-card">
      <span aria-hidden="true">404</span>
      <h1>Page not found</h1>
      <p>The requested route is not part of this fixture.</p>
      <Link className="primary-button" to="/">
        Return to workspace
      </Link>
    </section>
  );
}
