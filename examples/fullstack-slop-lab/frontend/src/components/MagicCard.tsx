import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
  title?: string;
  eyebrow?: string;
  action?: ReactNode;
};

export function MagicCard({
  children,
  className = "",
  title,
  eyebrow,
  action,
}: Props) {
  return (
    <section className={`magic-card glass-card ${className}`}>
      {(title || eyebrow || action) && (
        <div className="card-header">
          <div>
            {eyebrow && <span className="eyebrow">{eyebrow}</span>}
            {title && <h2>{title}</h2>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

