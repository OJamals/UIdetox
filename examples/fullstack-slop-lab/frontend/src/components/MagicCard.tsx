import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
  title?: string;
  eyebrow?: string;
  action?: ReactNode;
  subtitle?: string;
  badge?: string;
  icon?: string;
  tone?: string;
  tiny?: boolean;
  footer?: ReactNode;
};

export function OperationalSection({
  children,
  className = "",
  title,
  eyebrow,
  action,
  subtitle,
  badge,
  icon,
  tone = "default",
  tiny = false,
  footer,
}: Props) {
  return (
    <section className={`operational-section ${tone} ${tiny ? "compact" : ""} ${className}`}>
      {(title || eyebrow || subtitle || badge || icon || action) && (
        <header className="section-header">
          {icon ? <span aria-hidden="true" className="section-marker">{icon}</span> : null}
          <div>
            {eyebrow && <span className="eyebrow">{eyebrow}</span>}
            {title && <h2>{title}</h2>}
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          {badge ? <span className="status-pill">{badge}</span> : null}
          {action}
        </header>
      )}
      <div className="section-body">{children}</div>
      {footer ? <footer className="section-footer">{footer}</footer> : null}
    </section>
  );
}
