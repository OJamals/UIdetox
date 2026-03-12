"""Sub-agent session management: create, track, and record sub-agent work."""

import json
import logging
import os
import re
import shlex
import shutil
import uuid
from pathlib import Path

from uidetox.analyzer import IGNORE_DIRS # type: ignore
from uidetox.state import (
    get_uidetox_dir,
    ensure_uidetox_dir,
    load_state,
    load_config,
    batch_add_issues,
    _atomic_write_json,
) # type: ignore
from uidetox.utils import now_iso # type: ignore

logger = logging.getLogger(__name__)

STAGES = ["observe", "diagnose", "prioritize", "fix", "verify", "review"]

# ── Reference-driven scoring rubric ──────────────────────────────
#
# Domain sharding for parallel subjective review — 10 fine-grained
# domains organized as 2 waves of 5.  Each domain maps to reference
# files and the review rubric sections it evaluates.  Splitting into
# 10 (vs. the original 5) gives each subagent a narrower, deeper
# focus and yields more thorough coverage of the subjective rubric
# which accounts for 70% of the blended Design Score.
#
# Every domain now carries:
#   • ``checklist``  – concrete items the reviewer MUST verify (derived
#     from the reference files so scoring is consistent across agents)
#   • ``thresholds`` – hard numeric thresholds that act as pass/fail
#     gates — the reviewer must cite measurements for each
#   • ``deductions`` – specific anti-patterns that trigger automatic
#     point deductions (prevents score inflation)
#
# Wave 1 — Audit & Analysis (visual surface, interaction, content)
# Wave 2 — System & Architecture (consistency, identity, code quality)

REVIEW_DOMAINS: list[dict] = [
    # ── Wave 1: Audit & Analysis ──────────────────────────────────
    {
        "name": "typography",
        "label": "Typography & Type Hierarchy",
        "wave": 1,
        "references": ["reference/typography.md"],
        "rubric": "A.TYPOGRAPHY (0-10) = 10 pts",
        "max_score": 10,
        "focus": "Font families, weight spectrum (avoid only 400/700), optical sizing, "
                 "type scale (major-third / perfect-fourth), kerning, tracking, "
                 "line-height, paragraph rhythm, heading hierarchy, text contrast.",
        "checklist": [
            "Vertical rhythm: line-height is the base unit for ALL vertical spacing",
            "Modular scale: ≤5 font sizes with clear ratio (1.25/1.333/1.5)",
            "Measure: max-width: 65ch on body text containers",
            "Weight spectrum uses 500/600, not just 400+700",
            "Semantic token names (--text-body, --text-heading), not --font-size-16",
            "Font loading: font-display: swap + fallback size-adjust",
            "Fluid type: clamp() for headings, NOT for buttons/labels/UI",
            "Dark backgrounds increase line-height by +0.05-0.1",
            "OpenType: tabular-nums for data, diagonal-fractions, small-caps for abbr",
            "Body text uses rem/em, never px",
        ],
        "thresholds": {
            "min_body_text_size": "16px",
            "max_line_length": "65ch",
            "max_font_families": 3,
            "scale_ratios": "1.25 (major-third) | 1.333 (perfect-fourth) | 1.5 (perfect-fifth)",
            "dark_bg_line_height_boost": "+0.05-0.1",
        },
        "deductions": [
            "-3 pts: banned fonts as primary (Inter, Roboto, Arial, Open Sans, Lato, Montserrat)",
            "-2 pts: only Regular (400) and Bold (700) weights used",
            "-2 pts: body text < 16px or in px units",
            "-1 pt: > 3 font families",
            "-1 pt: missing font-display: swap",
            "-1 pt: serif fonts on dashboard/data UI",
        ],
    },
    {
        "name": "color_contrast",
        "label": "Color & Contrast",
        "wave": 1,
        "references": ["reference/color-and-contrast.md", "reference/color-palettes.md"],
        "rubric": "A.STYLING & ELEGANCE — color sub-section (0-8) = 8 pts",
        "max_score": 8,
        "focus": "Palette cohesion, contrast ratios (WCAG AA/AAA), dark mode support, "
                 "accent usage, gradient restraint, semantic color tokens, CSS variable "
                 "coverage, purple-blue gradient detection (AI slop fingerprint #1).",
        "checklist": [
            "OKLCH preferred over HSL for perceptual uniformity",
            "60-30-10 rule: 60% neutral, 30% secondary, 10% accent",
            "All neutrals have brand tint (chroma ~0.01), never pure gray",
            "Two-layer tokens: primitive (--blue-500) + semantic (--color-primary)",
            "Dark mode is NOT inverted light mode — separate design decisions",
            "Dark mode: lighter surfaces, desaturated accents, reduced font weight (350)",
            "Dark mode background lightness: 12-18% OKLCH, never pure black",
            "No reliance on color alone to convey information (colorblind-safe)",
            "Focus ring contrast ≥ 3:1 against adjacent colors",
            "Placeholder text contrast same as body text (4.5:1)",
        ],
        "thresholds": {
            "body_text_contrast_aa": "4.5:1",
            "body_text_contrast_aaa": "7:1",
            "large_text_contrast_aa": "3:1 (18px+ or 14px bold)",
            "ui_component_contrast_aa": "3:1",
            "focus_ring_contrast": "3:1",
            "dark_mode_bg_lightness": "12-18% OKLCH",
            "tinted_neutral_chroma": "~0.01",
            "max_accent_saturation": "< 80%",
            "pure_black_ban": "never #000000",
            "pure_white_ban": "never #ffffff",
        },
        "deductions": [
            "-3 pts: light gray text on white (WCAG fail)",
            "-2 pts: purple-blue gradient (AI slop fingerprint #1)",
            "-2 pts: pure #000000 or #ffffff used",
            "-2 pts: accent saturation > 80%",
            "-1 pt: neon/outer glow effects",
            "-1 pt: gradient text on headings",
            "-1 pt: relying on color alone for meaning",
        ],
    },
    {
        "name": "interaction_states",
        "label": "Interaction & Component States",
        "wave": 1,
        "references": ["reference/interaction-design.md"],
        "rubric": "C.STATES & MICRO-INTERACTIONS (0-10) = 10 pts",
        "max_score": 10,
        "focus": "Hover/focus/active/disabled/loading/empty/error states, keyboard "
                 "navigation, focus ring visibility, skip-to-content, ARIA labels, "
                 "icon-only button accessibility, touch target sizing.",
        "checklist": [
            "8 interactive states: default, hover, focus, active, disabled, loading, error, success",
            "Focus rings: :focus-visible only, 2-3px thick, offset, high contrast",
            "Never outline:none without replacement",
            "Placeholders are NOT labels — visible <label> always present",
            "Validate on blur, not per-keystroke (except password strength)",
            "Errors below fields with aria-describedby",
            "Skeleton screens preferred over spinners",
            "Native <dialog> + inert for modals with focus trapping",
            "Roving tabindex for component groups (tabs, menus, radio)",
            "Skip-to-content link present",
            "Icon-only buttons have aria-label",
            "Undo preferred over confirmation dialogs (low-stakes actions)",
        ],
        "thresholds": {
            "min_touch_target": "44×44px",
            "focus_ring_thickness": "2-3px",
            "focus_ring_contrast": "3:1",
        },
        "deductions": [
            "-3 pts: outline:none without replacement (keyboard users locked out)",
            "-2 pts: missing focus states entirely",
            "-2 pts: touch targets < 44px",
            "-2 pts: hover states without matching focus states",
            "-1 pt: placeholder text used as label",
            "-1 pt: generic spinners instead of skeleton screens",
            "-1 pt: icon buttons without aria-label",
        ],
    },
    {
        "name": "content_ux_writing",
        "label": "Content & UX Writing",
        "wave": 1,
        "references": ["reference/ux-writing.md"],
        "rubric": "D.CONTENT QUALITY (0-5) = 5 pts",
        "max_score": 5,
        "focus": "Microcopy quality, error messages, placeholder data realism, "
                 "button labels, confirmation dialogs, tone consistency, "
                 "exclamation mark abuse, generic 'Lorem ipsum' detection.",
        "checklist": [
            "Buttons: specific verb + object ('Save changes', not 'OK'/'Submit')",
            "Destructive actions name the destruction ('Delete 5 items')",
            "Error formula: What happened → Why → How to fix",
            "Never blame the user in error messages",
            "Empty states are onboarding: acknowledge + explain value + CTA",
            "Voice consistent, tone adapts (celebratory/empathetic/reassuring)",
            "Link text has standalone meaning ('View pricing plans', not 'Click here')",
            "Alt text describes information, not images; decorative → alt=''",
            "Terminology consistency: pick one term, use it everywhere",
            "Loading states are specific ('Saving your draft…' not 'Loading…')",
            "No humor for errors, no exclamation marks in success messages",
        ],
        "thresholds": {
            "i18n_expansion_german": "+30%",
            "i18n_expansion_french": "+20%",
        },
        "deductions": [
            "-2 pts: Lorem Ipsum present",
            "-2 pts: generic 'OK'/'Submit'/'Yes'/'No' buttons",
            "-1 pt: 'Something went wrong' or 'Oops!' error messages",
            "-1 pt: 'Click here' link text",
            "-1 pt: generic placeholder names (John Doe, Jane Smith, Acme Corp)",
            "-1 pt: AI clichés (Elevate, Seamless, Unleash, Next-Gen, Delve)",
            "-1 pt: round placeholder numbers (99.99%, 50%, $100)",
        ],
    },
    {
        "name": "motion_animation",
        "label": "Motion & Animation Design",
        "wave": 1,
        "references": ["reference/motion-design.md"],
        "rubric": "C.EDGE CASES & POLISH — motion sub-section (0-7) = 7 pts",
        "max_score": 7,
        "focus": "Transition timing (150-300ms sweet spot), easing curves "
                 "(ease-out-quart preferred), entrance/exit choreography, "
                 "scroll-triggered animations, skeleton screens, loading "
                 "state transitions, reduced-motion media query support.",
        "checklist": [
            "100-150ms: instant feedback (button, toggle, color)",
            "200-300ms: state changes (menu, tooltip, hover)",
            "300-500ms: layout changes (accordion, modal, drawer)",
            "500-800ms: entrance animations (page load, hero)",
            "Exit = ~75% of enter duration",
            "Easing: ease-out for enter, ease-in for leave, ease-in-out for toggles",
            "Default easing: ease-out-quart cubic-bezier(0.25, 1, 0.5, 1)",
            "Only animate transform and opacity (never width/height/top/left)",
            "Height animation via grid-template-rows: 0fr → 1fr",
            "Stagger cap: 10 items × 50ms = 500ms max",
            "@media (prefers-reduced-motion: reduce) present — crossfade alternatives",
            "Motion tokens defined for consistency (--duration-fast, --ease-out)",
        ],
        "thresholds": {
            "instant_feedback": "100-150ms",
            "state_change": "200-300ms",
            "layout_change": "300-500ms",
            "entrance_animation": "500-800ms",
            "exit_ratio": "~75% of enter",
            "perception_threshold": "80ms",
            "max_stagger_total": "500ms",
            "default_easing": "cubic-bezier(0.25, 1, 0.5, 1)",
        },
        "deductions": [
            "-3 pts: prefers-reduced-motion not handled at all",
            "-2 pts: bounce/elastic easing used",
            "-2 pts: animating width/height/top/left (layout thrashing)",
            "-1 pt: >500ms for UI feedback",
            "-1 pt: linear easing (no deceleration curve)",
            "-1 pt: will-change used preemptively",
        ],
    },
    {
        "name": "design_elegance",
        "label": "Design Elegance & Craft",
        "wave": 1,
        "references": ["reference/creative-arsenal.md", "reference/anti-patterns.md"],
        "rubric": "A.DESIGN ELEGANCE & CRAFT (0-10) = 10 pts",
        "max_score": 10,
        "focus": "Holistic aesthetic quality, visual harmony, intentional micro-details, "
                 "professional finishing, cohesive visual language, craft in every pixel. "
                 "Does this feel designed or assembled? Would a design director approve?",
        "checklist": [
            "Visual hierarchy clear without reading — squint test passes across all pages",
            "Color palette feels intentional, not randomly assembled from framework defaults",
            "Whitespace is used as a design element, not just gaps between elements",
            "Custom micro-details: selection colors, scrollbar styling, text decoration",
            "Visual rhythm: repeating spacing/alignment patterns create intentional cadence",
            "Typography and color reinforce information hierarchy in concert",
            "No 'template' feel — design has a distinctive aesthetic point of view",
            "Transitions and interactions feel cohesive (unified easing, consistent timing)",
            "Dark mode is a considered redesign (not a CSS filter/color inversion)",
            "Custom empty/error/loading states — no browser defaults visible anywhere",
            "Overall: would a professional designer approve without requests for changes?",
        ],
        "thresholds": {
            "visual_cohesion": "All pages share same spacing scale, type system, and color palette",
            "detail_level": "≥5 micro-details present (selection color, scrollbar, link underlines, hover states, focus rings)",
            "hierarchy_dimensions": "≥3 hierarchy tools used together (size + weight + color + spacing)",
            "aesthetic_consistency": "Cross-page visual language is unified (nav, footer, headings, cards)",
        },
        "deductions": [
            "-4 pts: immediate 'AI-generated' or 'template' impression (fails the squint test)",
            "-3 pts: no cohesive visual language — pages/sections feel assembled from parts",
            "-2 pts: whitespace used inconsistently or not as a deliberate design tool",
            "-2 pts: micro-details missing (default selection, native scrollbars, default underlines)",
            "-1 pt: dark mode is just inverted light mode (same lightness relationships)",
            "-1 pt: hierarchy relies on size alone (no weight/color/spacing variation)",
            "-1 pt: inconsistent visual density across pages (one sparse, one cramped)",
        ],
    },
    {
        "name": "accessibility",
        "label": "Accessibility & Inclusive Design",
        "wave": 1,
        "references": ["reference/interaction-design.md", "reference/ux-writing.md"],
        "rubric": "C.ACCESSIBILITY & INCLUSIVE DESIGN (0-10) = 10 pts",
        "max_score": 10,
        "focus": "WCAG 2.2 Level AA compliance, semantic HTML structure, landmark "
                 "regions, keyboard navigation completeness, screen reader UX, "
                 "reduced motion respect, color independence, touch targets, "
                 "focus management, heading hierarchy, alt text quality.",
        "checklist": [
            "All pages have <main>, <nav>, <header>, <footer> landmarks",
            "Heading hierarchy: single <h1>, sequential nesting (no h1→h3 skip)",
            "All interactive elements reachable and operable via keyboard alone",
            "Focus order matches visual order (no tabindex > 0)",
            "All non-text content has text alternatives (alt, aria-label, aria-describedby)",
            "<html lang> attribute present and correct",
            "Skip-to-content link as first focusable element",
            "ARIA attributes used correctly (no aria-label on non-interactive divs)",
            "Live regions (aria-live) for dynamic content updates (toasts, notifications)",
            "color-scheme meta tag and prefers-color-scheme support",
            "prefers-reduced-motion media query with crossfade alternatives",
            "prefers-contrast media query support for high-contrast needs",
            "No autoplaying media without user control",
            "Form error announcements linked to fields via aria-describedby",
        ],
        "thresholds": {
            "wcag_level": "AA (minimum), AAA preferred for text contrast",
            "keyboard_trap_free": "100% — zero keyboard traps in any flow",
            "landmark_coverage": "100% of page content within landmarks",
            "heading_sequence": "100% sequential (no skipped levels)",
            "focus_visible_coverage": "100% of interactive elements have :focus-visible",
        },
        "deductions": [
            "-3 pts: keyboard navigation broken (traps, unreachable elements)",
            "-3 pts: no landmark regions at all (<main>, <nav>, etc.)",
            "-2 pts: heading hierarchy broken (skipped levels or multiple h1)",
            "-2 pts: images without alt text (non-decorative)",
            "-2 pts: no prefers-reduced-motion support",
            "-1 pt: no <html lang> attribute",
            "-1 pt: ARIA misuse (wrong roles, redundant/conflicting labels)",
            "-1 pt: no skip-to-content link",
            "-1 pt: focus order doesn't match visual order",
            "-1 pt: no prefers-contrast support",
        ],
    },
    # ── Wave 2: System & Architecture ─────────────────────────────
    {
        "name": "spatial_layout",
        "label": "Spatial Design & Layout",
        "wave": 2,
        "references": ["reference/spatial-design.md"],
        "rubric": "A.LAYOUT & SPATIAL DESIGN (0-15) = 15 pts",
        "max_score": 15,
        "focus": "Grid systems (CSS Grid vs. Flexbox), whitespace rhythm, "
                 "alignment consistency, spacing scale (4px base), "
                 "asymmetric layout where DESIGN_VARIANCE > 4, container "
                 "max-widths, padding/margin patterns, viewport units.",
        "checklist": [
            "4pt base spacing scale: 4, 8, 12, 16, 24, 32, 48, 64, 96px",
            "Semantic spacing tokens (--space-sm, --space-lg), not --spacing-8",
            "gap instead of margins for sibling spacing",
            "Self-adjusting grid: repeat(auto-fit, minmax(280px, 1fr))",
            "Named grid areas for complex layouts",
            "Squint test passes: clear hierarchy at a glance",
            "Hierarchy via 2-3 dimensions (size + weight + color), not size alone",
            "Size hierarchy ratio ≥ 3:1 for strong visual weight",
            "Cards only for distinct, actionable content — never nested",
            "Container queries for components, viewport queries for pages",
            "Optical adjustments: -0.05em on text margin-left",
            "z-index uses semantic scale (dropdown→sticky→modal→toast→tooltip)",
            "Subtle shadows: if you can clearly see it, it is too strong",
        ],
        "thresholds": {
            "base_spacing_unit": "4px",
            "spacing_scale": "4, 8, 12, 16, 24, 32, 48, 64, 96px",
            "min_grid_column": "280px (auto-fit)",
            "min_touch_target": "44px",
            "strong_hierarchy_ratio": "≥ 3:1",
            "weak_hierarchy_ratio": "< 2:1",
            "max_width_container": "1200-1440px",
            "full_section_height": "min-height: 100dvh (NOT 100vh)",
        },
        "deductions": [
            "-3 pts: arbitrary spacing outside scale system",
            "-3 pts: no max-width container (content spans full viewport)",
            "-2 pts: cards nested inside cards",
            "-2 pts: height: 100vh instead of min-height: 100dvh",
            "-2 pts: all spacing uniform (no rhythm/hierarchy)",
            "-1 pt: arbitrary z-index (9999)",
            "-1 pt: cards used for everything",
            "-1 pt: hierarchy via size alone (ratio < 2:1)",
        ],
    },
    {
        "name": "materiality_surfaces",
        "label": "Materiality & Surfaces",
        "wave": 2,
        "references": ["reference/color-and-contrast.md", "reference/creative-arsenal.md"],
        "rubric": "A.STYLING & ELEGANCE — surface sub-section (0-7) = 7 pts",
        "max_score": 7,
        "focus": "Shadow craft (shadow-sm/md hierarchy), border usage, "
                 "surface texture, glassmorphism detection (AI slop), "
                 "border-radius consistency, neon glow elimination, "
                 "gradient text removal, solid surface preference.",
        "checklist": [
            "Shadow hierarchy: sm/md levels, never 2xl/3xl",
            "Shadows are tinted (not pure gray/black)",
            "Border-radius consistent: 8-12px max for most elements",
            "Glassmorphism reserved for intentional depth, not everywhere",
            "Glassmorphism done right: backdrop-blur + 1px inner border-white/10 + inner shadow",
            "No outer glows / box-shadow glows — use inner borders, tinted shadows",
            "No gradient text on headings — solid color with weight",
            "Surface textures are subtle (grain/noise overlays if any)",
            "Alpha/transparency is a design smell — define explicit overlay colors",
            "Solid opaque borders use /50 opacity for dividers",
        ],
        "thresholds": {
            "max_border_radius": "8-12px",
            "shadow_hierarchy": "sm → md only",
        },
        "deductions": [
            "-3 pts: glassmorphism/backdrop-blur used everywhere",
            "-2 pts: border-radius 20-32px on most elements",
            "-2 pts: neon accents or outer glows",
            "-1 pt: gradient text",
            "-1 pt: oversized shadows (2xl/3xl)",
            "-1 pt: pure gray shadows (not tinted)",
        ],
    },
    {
        "name": "consistency_system",
        "label": "Design System & Consistency",
        "wave": 2,
        "references": ["reference/anti-patterns.md"],
        "rubric": "B.CONSISTENCY (0-15) = 15 pts",
        "max_score": 15,
        "focus": "Unified design tokens, spacing scale consistency, "
                 "color palette adherence, component pattern uniformity, "
                 "variant drift detection, duplicated className strings, "
                 "copy-pasted markup, media query deduplication.",
        "checklist": [
            "Design tokens defined and used consistently across all components",
            "Spacing scale adhered to everywhere (no ad-hoc px values)",
            "Color palette is unified — all colors traced to tokens",
            "Same component looks identical everywhere (no variant drift)",
            "No duplicated className strings across files",
            "No copy-pasted markup blocks that should be components",
            "Media queries deduplicated and use consistent breakpoints",
            "Semantic HTML: nav, main, article, aside (not div soup)",
            "Consistent naming conventions (kebab vs camel for tokens)",
            "AI slop test: would someone immediately believe AI made this?",
        ],
        "thresholds": {},
        "deductions": [
            "-3 pts: no design tokens — raw values scattered everywhere",
            "-3 pts: same component looks different in different places",
            "-2 pts: div soup (no semantic HTML)",
            "-2 pts: inline styles mixed with utility classes",
            "-1 pt: duplicate className strings across files",
            "-1 pt: > 3 different breakpoint sets in media queries",
            "-1 pt: commented-out dead code left in production",
        ],
    },
    {
        "name": "identity_brand",
        "label": "Identity & Brand Coherence",
        "wave": 2,
        "references": ["reference/creative-arsenal.md", "reference/anti-patterns.md"],
        "rubric": "B.IDENTITY (0-15) = 15 pts",
        "max_score": 15,
        "focus": "Does this feel designed or generated? Intentional aesthetic "
                 "presence, AI slop fingerprints (Inter font, purple-blue "
                 "gradients, glassmorphism, Unsplash hero), brand personality, "
                 "visual voice consistency, icon system coherence.",
        "checklist": [
            "Distinct aesthetic point-of-view (would someone ask 'who designed this?')",
            "No AI slop fingerprints (Inter + purple gradient + glassmorphism + Unsplash hero)",
            "Icon system is unified (one library, consistent size/stroke)",
            "Brand personality present — not generic template feel",
            "Visual voice consistency across all pages/sections",
            "Custom 404 page exists",
            "Custom loading/empty/error states (not browser defaults)",
            "Favicon present and brand-aligned",
            "Missing strategic elements checked: legal links, skip-to-content, meta tags",
            "Placeholder content feels realistic, not AI-generated",
        ],
        "thresholds": {},
        "deductions": [
            "-4 pts: immediate AI-generated feel (fails the AI slop test)",
            "-3 pts: 3+ AI slop fingerprints present (Inter/purple-gradient/glassmorphism/Unsplash)",
            "-2 pts: generic template feel with no design personality",
            "-2 pts: mixed icon libraries (Lucide + Heroicons + custom)",
            "-1 pt: broken Unsplash links or generic stock images",
            "-1 pt: missing favicon",
            "-1 pt: missing meta tags (title, description, og:image)",
            "-1 pt: emojis used in production UI markup",
        ],
    },
    {
        "name": "architecture_responsive",
        "label": "Responsive Design & Code Architecture",
        "wave": 2,
        "references": ["reference/responsive-design.md"],
        "rubric": "D.ARCHITECTURE & CODE QUALITY (0-8) = 8 pts",
        "max_score": 8,
        "focus": "Component structure, file organization, naming conventions, "
                 "separation of concerns, reusability, responsive breakpoints, "
                 "min-h-[100dvh] usage, z-index scale, semantic HTML5, "
                 "DTO alignment, data flow, error surfacing.",
        "checklist": [
            "Mobile-first: base styles for mobile, complexity added via min-width",
            "Content-driven breakpoints (not device-chasing)",
            "≤ 3 breakpoints usually sufficient (640, 768, 1024px)",
            "clamp() for fluid values without breakpoints",
            "Input method detection: @media (pointer: fine/coarse), (hover: hover/none)",
            "Safe areas: env(safe-area-inset-*) + viewport-fit=cover",
            "Responsive images: srcset + sizes, <picture> for art direction",
            "Navigation adapts: hamburger (mobile) → compact (tablet) → full (desktop)",
            "Tables convert to cards on mobile (display: block + data-label)",
            "Component structure: separation of concerns, reusability, composability",
            "Hardcoded px widths replaced with relative units (%/rem/max-width)",
            "Import paths verified against package.json (no hallucinations)",
        ],
        "thresholds": {
            "common_breakpoints": "640, 768, 1024px",
            "touch_target_coarse": "padding: 12px 20px",
            "fine_pointer_padding": "padding: 8px 16px",
            "viewport_meta": "width=device-width, initial-scale=1, viewport-fit=cover",
        },
        "deductions": [
            "-3 pts: desktop-first design (max-width queries instead of min-width)",
            "-2 pts: no responsive behavior at all",
            "-2 pts: import hallucinations (packages not in package.json)",
            "-1 pt: 100vh instead of 100dvh (broken on iOS Safari)",
            "-1 pt: hardcoded px widths for layout containers",
            "-1 pt: hover relied upon for core functionality",
        ],
    },
    {
        "name": "api_data_coherence",
        "label": "API & Data Coherence",
        "wave": 2,
        "references": ["reference/interaction-design.md", "reference/responsive-design.md"],
        "rubric": "D.API & DATA COHERENCE (0-10) = 10 pts",
        "max_score": 10,
        "focus": "Frontend-backend alignment, DTO field matching, data flow "
                 "architecture, caching strategy, optimistic updates, "
                 "error/loading/empty state coherence with actual API behavior, "
                 "type safety across boundaries, database schema alignment.",
        "checklist": [
            "Frontend types match backend DTOs field-for-field (no phantom fields)",
            "Nullable/optional fields handled explicitly (not assumed non-null)",
            "All API responses have defined TypeScript types (never 'any')",
            "Loading states reflect actual backend latency (skeleton screens, not spinners)",
            "Error states handle ALL backend status codes (400, 401, 403, 404, 422, 500)",
            "Empty states match zero-result API responses (not just generic 'No data')",
            "Form validation mirrors backend constraints (length, format, range, required)",
            "Pagination/sort/filter params align with backend query API",
            "Optimistic updates have rollback on server rejection",
            "Data caching strategy is deliberate (SWR/React Query/RTK Query with stale times)",
            "Enum values synchronized between frontend and backend/database",
            "Date/time format handling consistent (ISO 8601, timezone-aware)",
        ],
        "thresholds": {
            "type_coverage": "100% of API responses have typed interfaces",
            "error_handling": "All 4xx and 5xx codes handled with user-facing messages",
            "state_completeness": "100% of data-fetching surfaces handle loading/error/empty",
            "validation_alignment": "100% of form fields validate client-side matching server rules",
        },
        "deductions": [
            "-3 pts: 'any' type used for API responses",
            "-3 pts: no error handling on data-fetching surfaces",
            "-2 pts: frontend types have fields the backend doesn't send (phantom fields)",
            "-2 pts: generic 'Something went wrong' for all API errors",
            "-2 pts: no loading states on data-fetching components",
            "-1 pt: nullable fields assumed non-null without runtime guards",
            "-1 pt: no caching strategy (fresh fetch every render)",
            "-1 pt: date handling inconsistent (mixing formats, no timezone handling)",
            "-1 pt: pagination not synchronized with backend API",
        ],
    },
    {
        "name": "performance_vitals",
        "label": "Performance & Web Vitals",
        "wave": 2,
        "references": ["reference/responsive-design.md"],
        "rubric": "D.PERFORMANCE & WEB VITALS (0-8) = 8 pts",
        "max_score": 8,
        "focus": "Core Web Vitals targets (LCP, CLS, INP), bundle optimization, "
                 "lazy loading, image optimization, render performance, "
                 "code splitting, proper asset handling, unnecessary re-render "
                 "prevention, virtualization for large lists.",
        "checklist": [
            "Images use next-gen formats (WebP/AVIF) with fallbacks",
            "Images have explicit width/height or aspect-ratio to prevent CLS",
            "Above-fold images use priority/eager loading; below-fold use lazy",
            "Heavy components code-split (React.lazy, dynamic import())",
            "CSS and JS tree-shaken (no unused imports shipping to production)",
            "Fonts use font-display: swap with fallback size-adjust",
            "No render-blocking resources in critical path",
            "Expensive computations memoized appropriately (useMemo/useCallback)",
            "Lists >50 items use virtualization (react-window, TanStack Virtual)",
            "No layout thrashing (reading then writing DOM in loops)",
            "Bundle size reasonable: main chunk <200KB gzipped",
            "Prefetching/preloading for predictable navigation paths",
        ],
        "thresholds": {
            "lcp_target": "≤ 2.5s",
            "cls_target": "≤ 0.1",
            "inp_target": "≤ 200ms",
            "main_bundle_gzip": "< 200KB",
            "image_format": "WebP or AVIF preferred",
            "lazy_load_threshold": "Images below first viewport",
        },
        "deductions": [
            "-3 pts: no image optimization (no srcset, no lazy loading, no next-gen formats)",
            "-2 pts: layout shift sources (images without dimensions, dynamic content without placeholders)",
            "-2 pts: render-blocking resources without mitigation (no async/defer)",
            "-2 pts: giant bundle (>500KB gzipped main chunk)",
            "-1 pt: no code splitting on route level",
            "-1 pt: unnecessary re-renders (missing memo/callback for expensive operations)",
            "-1 pt: no font optimization (font-display, size-adjust missing)",
            "-1 pt: lists >50 items without virtualization",
        ],
    },
    # ── Cross-Cutting Perfection Gate ─────────────────────────────
    #
    # This domain is NOT scored independently — it acts as a multiplier
    # gate that caps the final normalized score.  If ANY gate condition
    # fails, the reviewer MUST cap the final score at 85 maximum.
    # If 2+ conditions fail, cap at 75.  Only when ALL conditions pass
    # can the final score exceed 85.
    {
        "name": "perfection_gate",
        "label": "Perfection Gate (ceiling enforcer)",
        "wave": 0,  # evaluated last, across all waves
        "references": [],
        "rubric": "GATE — not scored; caps total when conditions fail",
        "max_score": 0,  # no additive points
        "focus": "Cross-cutting quality gates that MUST all pass before the "
                 "final score can exceed 85.  These are non-negotiable "
                 "perfection requirements — a single failure here means "
                 "the codebase is NOT perfect, regardless of domain scores.",
        "checklist": [
            "ZERO pending issues in `uidetox status` queue",
            "ZERO lint errors or TypeScript errors (`uidetox check` passes clean)",
            "ZERO console.log / console.warn remaining in production code",
            "ZERO TODO/FIXME comments remaining",
            "ZERO commented-out code blocks",
            "ZERO unused imports",
            "ZERO AI slop fingerprints (Inter font, purple gradient, glassmorphism combo)",
            "ALL interactive elements have hover + focus + active + disabled states",
            "ALL images have alt text (decorative → alt='')",
            "ALL forms have visible labels (not placeholder-as-label)",
            "ALL pages have semantic landmarks (<main>, <nav>, <header>, <footer>)",
            "ALL heading hierarchy is sequential (single h1, no skipped levels)",
            "ALL images optimized (srcset, lazy loading, next-gen formats or size-adjust)",
            "ALL API responses have typed interfaces (no 'any' for data)",
            "ZERO phantom types (frontend interfaces with fields backend doesn't send)",
            "prefers-reduced-motion media query present",
            "prefers-color-scheme media query present (or CSS custom-property toggle)",
            "Skip-to-content link present",
            "Favicon present",
            "Meta tags present (title, description, og:image)",
            "Custom 404 page exists",
            "No hardcoded px for font sizes (rem/em only)",
            "No render-blocking resources without async/defer mitigation",
        ],
        "thresholds": {},
        "deductions": [
            "GATE FAIL: cap at 85 if 1 condition fails",
            "GATE FAIL: cap at 75 if 2-3 conditions fail",
            "GATE FAIL: cap at 65 if 4+ conditions fail",
        ],
    },
]

# Quick lookup: how many domains per wave (excludes perfection gate wave 0)
REVIEW_WAVE_1 = [d for d in REVIEW_DOMAINS if d.get("wave") == 1]
REVIEW_WAVE_2 = [d for d in REVIEW_DOMAINS if d.get("wave") == 2]
# Scored domains only (excludes the perfection gate which has max_score=0)
SCORED_REVIEW_DOMAINS = [d for d in REVIEW_DOMAINS if d.get("max_score", 0) > 0]
PERFECTION_GATE = next((d for d in REVIEW_DOMAINS if d.get("name") == "perfection_gate"), None)


def _coerce_parallel(parallel: int) -> int:
    return max(1, int(parallel or 1))


# ── Complexity scoring for workload-aware sharding ───────────────

_TIER_COMPLEXITY = {"T1": 1, "T2": 3, "T3": 5, "T4": 8}
_FIX_TIER_PRIORITY = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
_FIX_TIER_WORKLOAD = {"T1": 8, "T2": 5, "T3": 3, "T4": 1}


def _file_complexity_score(filepath: str, issues: list[dict] | None = None) -> float:
    """Compute a complexity score for a file based on size, issue count/tier, and coupling.

    Higher scores → more review/fix effort required.

    Components:
        1. File size (bytes / 1000, capped at 20)
        2. Issue weight (sum of tier weights for issues in this file)
        3. Import coupling (number of local imports, capped at 10)
    """
    from pathlib import Path as _Path

    score = 0.0

    # 1. File size component
    try:
        size = _Path(filepath).stat().st_size
        score += min(20.0, size / 1000)
    except OSError:
        score += 5.0  # Default if unreadable

    # 2. Issue weight component
    if issues:
        for issue in issues:
            if issue.get("file", "") == filepath:
                tier = issue.get("tier", "T4")
                score += _TIER_COMPLEXITY.get(tier, 1)

    # 3. Import coupling component
    try:
        import_count = 0
        with open(filepath, encoding="utf-8", errors="ignore") as fh:
            for line_no, line in enumerate(fh):
                if line_no >= 100:
                    break
                stripped = line.strip()
                if stripped.startswith("import ") and ("'./" in stripped or '"./' in stripped or "'../" in stripped or '"../' in stripped):
                    import_count += 1
        score += min(10.0, import_count * 1.5)
    except OSError:
        pass

    return round(score, 2)


def _shard_items(items: list, parallel: int) -> list[list]:
    """Distribute items round-robin into balanced non-empty shards.

    For backward compatibility this function is still available.
    Use ``_shard_items_by_workload`` for complexity-aware sharding.
    """
    shard_count = min(len(items), _coerce_parallel(parallel))
    if shard_count <= 0:
        return []
    shards: list[list] = [[] for _ in range(shard_count)]
    for idx, item in enumerate(items):
        shards[idx % shard_count].append(item)
    return [shard for shard in shards if shard]


def _issue_group_priority(group: list[dict]) -> int:
    """Urgency key for selecting top fix groups (lower means more urgent)."""
    return min(_FIX_TIER_PRIORITY.get(issue.get("tier", "T4"), 5) for issue in group)


def _issue_group_workload(group: list[dict]) -> int:
    """Compute fix workload for a grouped file issue batch."""
    severity_score = sum(_FIX_TIER_WORKLOAD.get(issue.get("tier", "T4"), 1) for issue in group)
    issue_count_score = len(group)
    return severity_score + issue_count_score


def _shard_issue_groups_by_workload(
    groups: list[list[dict]],
    parallel: int,
) -> list[list[list[dict]]]:
    """Greedy weighted assignment for fix-stage grouped issues."""
    shard_count = min(len(groups), _coerce_parallel(parallel))
    if shard_count <= 0:
        return []

    indexed_groups = list(enumerate(groups))
    ranked = sorted(
        indexed_groups,
        key=lambda item: (-_issue_group_workload(item[1]), item[0]),
    )

    shard_loads = [0] * shard_count
    shards: list[list[tuple[int, list[dict]]]] = [[] for _ in range(shard_count)]
    for original_idx, group in ranked:
        lightest = min(range(shard_count), key=lambda idx: (shard_loads[idx], idx))
        load = _issue_group_workload(group)
        shards[lightest].append((original_idx, group))
        shard_loads[lightest] += load

    ordered_shards: list[list[list[dict]]] = []
    for shard in shards:
        shard.sort(key=lambda item: item[0])
        ordered_shards.append([group for _, group in shard])

    return [shard for shard in ordered_shards if shard]


def _shard_items_by_workload(
    files: list[str],
    parallel: int,
    *,
    issues: list[dict] | None = None,
) -> list[list[str]]:
    """Distribute files into shards by balancing total complexity score.

    Instead of flat round-robin by domain count, this assigns each file
    to the shard with the lowest accumulated complexity so that no single
    shard is overloaded with large, highly-coupled, issue-dense files.

    1. Score every file with ``_file_complexity_score``.
    2. Sort files descending by score (heaviest first).
    3. Greedily assign each file to the lightest shard.
    """
    shard_count = min(len(files), _coerce_parallel(parallel))
    if shard_count <= 0:
        return []

    # Score and sort files (heaviest first for better bin-packing)
    scored = [(f, _file_complexity_score(f, issues)) for f in files]
    scored.sort(key=lambda x: x[1], reverse=True)

    shard_loads: list[float] = [0.0] * shard_count
    shards: list[list[str]] = [[] for _ in range(shard_count)]

    for filepath, score in scored:
        # Assign to lightest shard
        lightest = min(range(shard_count), key=lambda i: shard_loads[i])
        shards[lightest].append(filepath)
        shard_loads[lightest] += score

    # Preserve file coupling: group co-directory files into same shard
    # Post-pass: if files from the same directory ended up in different
    # shards, consolidate them (prevents merge conflicts).
    from pathlib import Path as _Path
    from collections import defaultdict

    dir_to_shard: dict[str, int] = {}
    file_shard_map: dict[str, int] = {}
    for shard_idx, shard_files in enumerate(shards):
        for f in shard_files:
            d = str(_Path(f).parent)
            file_shard_map[f] = shard_idx
            if d not in dir_to_shard:
                dir_to_shard[d] = shard_idx

    # Only consolidate if it doesn't create extreme imbalance
    max_load = max(shard_loads) if shard_loads else 1
    for shard_idx, shard_files in enumerate(shards):
        for f in list(shard_files):
            d = str(_Path(f).parent)
            target = dir_to_shard.get(d, shard_idx)
            if target != shard_idx and shard_loads[target] < max_load * 1.5:
                shards[shard_idx].remove(f)
                shards[target].append(f)
                score_val = _file_complexity_score(f, issues)
                shard_loads[shard_idx] -= score_val
                shard_loads[target] += score_val

    return [shard for shard in shards if shard]


def _sessions_dir() -> Path:
    d = get_uidetox_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rotate_sessions(max_sessions: int = 200) -> None:
    """Evict oldest session directories when count exceeds *max_sessions*."""
    sessions_dir = _sessions_dir()
    try:
        session_dirs = sorted(
            [d for d in sessions_dir.iterdir() if d.is_dir() and d.name.startswith("session_")],
            key=lambda d: d.stat().st_mtime,
        )
    except OSError:
        return
    if len(session_dirs) <= max_sessions:
        return
    for old in session_dirs[: len(session_dirs) - max_sessions]:
        shutil.rmtree(old, ignore_errors=True)


def _session_id() -> str:
    """Return a 12-hex-char session ID (collision-safe)."""
    return uuid.uuid4().hex[:12]


def create_session(stage: str, prompt: str) -> str:
    """Create a new sub-agent session with a generated prompt.

    Args:
        stage: One of the 5 stages (observe, diagnose, prioritize, fix, verify).
        prompt: The full prompt text for the sub-agent.

    Returns:
        The session ID.
    """
    session_id = _session_id()
    session_dir = _sessions_dir() / f"session_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)

    # Write prompt
    with open(session_dir / "prompt.md", "w", encoding="utf-8") as f:
        f.write(prompt)

    # Write metadata atomically
    meta = {
        "session_id": session_id,
        "stage": stage,
        "status": "pending",
        "created_at": now_iso(),
        "completed_at": None,
    }
    _atomic_write_json(session_dir / "meta.json", meta, dir=session_dir)

    # Housekeep old sessions
    _rotate_sessions()

    return session_id


_SEVERITY_TO_TIER = {
    "critical": "T1",
    "blocker": "T1",
    "urgent": "T1",
    "high": "T2",
    "major": "T2",
    "medium": "T3",
    "moderate": "T3",
    "low": "T4",
    "minor": "T4",
    "info": "T4",
    "informational": "T4",
    "p0": "T1",
    "p1": "T2",
    "p2": "T3",
    "p3": "T4",
}


def _normalize_tier(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"t1", "t2", "t3", "t4"}:
        return raw.upper()
    return _SEVERITY_TO_TIER.get(raw, "T3")


def _first_nonempty(candidate: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = candidate.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return ""


def _normalize_issue_candidate(candidate: dict, *, default_command: str) -> dict | None:
    file_path = _first_nonempty(candidate, ("file", "path", "file_path", "filepath", "target"))
    issue_text = _first_nonempty(candidate, ("issue", "description", "finding", "title", "message"))
    if not file_path or not issue_text:
        return None

    command = _first_nonempty(candidate, ("fix_command", "command", "fix", "remediation", "suggested_fix"))
    normalized = {
        "id": f"SUB-{uuid.uuid4().hex[:8].upper()}",
        "file": file_path,
        "tier": _normalize_tier(candidate.get("tier") or candidate.get("severity") or candidate.get("priority")),
        "issue": issue_text,
        "command": command or default_command,
    }
    return normalized


def _extract_issue_candidates(result: dict) -> list[dict]:
    candidates: list[dict] = []
    top_level_keys = ("issues", "new_issues", "queued_issues", "review_issues", "findings")
    for key in top_level_keys:
        value = result.get(key)
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))

    nested_keys = ("domain_results", "domains", "results", "shards")
    nested_issue_keys = ("issues", "findings", "new_issues")
    for key in nested_keys:
        value = result.get(key)
        if not isinstance(value, list):
            continue
        for entry in value:
            if not isinstance(entry, dict):
                continue
            for issues_key in nested_issue_keys:
                nested = entry.get(issues_key)
                if isinstance(nested, list):
                    candidates.extend(item for item in nested if isinstance(item, dict))

    issues_by_file = result.get("issues_by_file")
    if isinstance(issues_by_file, dict):
        for file_path, issue_values in issues_by_file.items():
            if not isinstance(file_path, str):
                continue
            if isinstance(issue_values, list):
                for value in issue_values:
                    if isinstance(value, str) and value.strip():
                        candidates.append({"file": file_path, "issue": value.strip()})
                    elif isinstance(value, dict):
                        merged = dict(value)
                        merged.setdefault("file", file_path)
                        candidates.append(merged)
    return candidates


def _extract_add_issue_commands(result: dict) -> list[dict]:
    parsed: list[dict] = []
    text_fields = (
        result.get("note"),
        result.get("output"),
        result.get("verification"),
        result.get("summary"),
    )
    for field in text_fields:
        if not isinstance(field, str) or "uidetox add-issue" not in field:
            continue
        for raw_line in field.splitlines():
            line = raw_line.strip().strip("`")
            if "uidetox add-issue" not in line:
                continue
            try:
                tokens = shlex.split(line)
            except ValueError:
                continue
            if len(tokens) < 2:
                continue
            file_path = ""
            tier = "T3"
            issue_text = ""
            fix_command = ""
            idx = 0
            while idx < len(tokens):
                token = tokens[idx]
                nxt = tokens[idx + 1] if idx + 1 < len(tokens) else ""
                if token == "--file" and nxt:
                    file_path = nxt
                    idx += 2
                    continue
                if token == "--tier" and nxt:
                    tier = nxt
                    idx += 2
                    continue
                if token == "--issue" and nxt:
                    issue_text = nxt
                    idx += 2
                    continue
                if token == "--fix-command" and nxt:
                    fix_command = nxt
                    idx += 2
                    continue
                idx += 1
            if file_path and issue_text:
                parsed.append(
                    {
                        "file": file_path,
                        "tier": tier,
                        "issue": issue_text,
                        "fix_command": fix_command,
                    }
                )
    return parsed


def _ingest_result_issues(result: dict, *, stage: str) -> dict[str, int]:
    stage_label = stage.strip().lower() if isinstance(stage, str) else "unknown"
    phase = f"subagent_{stage_label or 'unknown'}"
    default_command = "uidetox next"

    raw_candidates = _extract_issue_candidates(result)
    raw_candidates.extend(_extract_add_issue_commands(result))

    normalized: list[dict] = []
    seen: set[str] = set()
    for candidate in raw_candidates:
        issue = _normalize_issue_candidate(candidate, default_command=default_command)
        if issue is None:
            continue
        key = f"{issue['file']}::{issue['issue']}::{issue['tier']}"
        if key in seen:
            continue
        seen.add(key)
        normalized.append(issue)

    if not normalized:
        return {"submitted": 0, "added": 0, "updated": 0, "skipped": 0}

    result_stats = batch_add_issues(normalized, phase=phase)
    return {
        "submitted": len(normalized),
        "added": int(result_stats.get("added", 0)),
        "updated": int(result_stats.get("updated", 0)),
        "skipped": int(result_stats.get("skipped", 0)),
    }


def record_result(session_id: str, result: dict) -> bool:
    """Record the result of a sub-agent session.

    Args:
        session_id: The session to update.
        result: Dict with the sub-agent's findings (issues found, files changed, etc).

    Returns:
        True if recorded, False if session not found.
    """
    session_dir = _sessions_dir() / f"session_{session_id}"
    if not session_dir.exists():
        logger.warning(f"Session directory not found: {session_dir}")
        return False

    try:
        # Write result atomically
        _atomic_write_json(session_dir / "result.json", result, dir=session_dir)

        # Update meta
        meta_path = session_dir / "meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            # Corrupt or missing meta.json — rebuild minimal metadata
            meta = {
                "session_id": session_id,
                "stage": "unknown",
                "status": "pending",
                "created_at": now_iso(),
                "completed_at": None,
                "_recovered": True,
                "_recovery_reason": str(exc),
            }

        # Parse confidence score if provided (multiple formats supported)
        confidence = _extract_confidence(result)

        # Determine status based on confidence thresholds
        if confidence < 0.6:
            meta["status"] = "needs_human_review"
            meta["review_reason"] = "Very low confidence — agent is uncertain about fix quality"
        elif confidence < 0.85:
            meta["status"] = "completed_with_warnings"
            meta["review_reason"] = "Below confidence threshold — recommend verification"
        else:
            meta["status"] = "completed"
            meta["review_reason"] = None

        meta["confidence"] = confidence
        meta["completed_at"] = now_iso()

        # Track issues found and fixed for progress metrics
        if "issues_found" in result:
            meta["issues_found"] = result["issues_found"]
        if "issues_fixed" in result:
            meta["issues_fixed"] = result["issues_fixed"]
        if "files_modified" in result:
            meta["files_modified"] = result["files_modified"]

        stage_name = str(meta.get("stage", "")).strip()
        try:
            ingest_stats = _ingest_result_issues(result, stage=stage_name)
            meta["issues_ingest_submitted"] = ingest_stats["submitted"]
            meta["issues_ingested"] = ingest_stats["added"]
            meta["issues_ingest_updated"] = ingest_stats["updated"]
            meta["issues_ingest_skipped"] = ingest_stats["skipped"]
            if "issues_found" not in result and ingest_stats["submitted"] > 0:
                meta["issues_found"] = ingest_stats["submitted"]
        except Exception as exc:
            logger.error(f"Issue ingestion failed for session {session_id}: {exc}")

        _atomic_write_json(meta_path, meta, dir=session_dir)

        review_request_path = session_dir / "review_request.json"

        # Flag low-confidence results for human review
        if confidence < 0.85:
            _flag_for_review(session_id, meta, confidence)
        elif review_request_path.exists():
            review_request_path.unlink(missing_ok=True)

        # Log to memory for persistence
        try:
            from uidetox.memory import add_note
            add_note(
                f"[SESSION {session_id}] Stage: {meta.get('stage')}, "
                f"Confidence: {confidence:.2f}, Status: {meta['status']}, "
                f"Issues found: {meta.get('issues_found', 0)}, "
                f"Issues fixed: {meta.get('issues_fixed', 0)}"
            )
        except Exception:
            pass  # Non-critical

        return True
    except Exception as e:
        logger.error(f"Failed to record session result for {session_id}: {e}")
        return False


def _extract_confidence(result: dict) -> float:
    """Extract confidence score from result using multiple parsing strategies.

    Default is 0.5 (uncertain) — never assumes high confidence.
    This ensures unverified fixes are flagged for review rather
    than auto-resolved.
    """
    confidence = 0.5

    # Strategy 1: Explicit CONFIDENCE: field in the note
    text = result.get("note", "")
    m = re.search(r'CONFIDENCE:\s*(0\.\d+|1\.0|1)', text, re.IGNORECASE)
    if m:
        return float(m.group(1))

    # Strategy 2: Check for confidence in structured result data
    if "confidence" in result:
        try:
            return float(result["confidence"])
        except (ValueError, TypeError):
            pass

    # Strategy 3: Parse from verification output
    verify_text = result.get("verification", result.get("output", ""))
    if verify_text:
        m = re.search(r'(?:confidence|certainty|score)[\s:]*(?:is\s+)?(0\.\d+|1\.0)', verify_text, re.IGNORECASE)
        if m:
            return float(m.group(1))

    # Strategy 4: Infer from error/warning signals in the result
    all_text = json.dumps(result).lower()
    warning_signals = ["unsure", "might not", "could break", "not certain", "unclear",
                       "risky", "regression", "manual check", "verify manually"]
    warning_count = sum(1 for sig in warning_signals if sig in all_text)
    if warning_count >= 3:
        confidence = 0.5
    elif warning_count >= 2:
        confidence = 0.7
    elif warning_count >= 1:
        confidence = 0.85

    return confidence


def _flag_for_review(session_id: str, meta: dict, confidence: float):
    """Flag a low-confidence session for human review.

    Creates a review request file and logs to memory for visibility.
    """
    session_dir = _sessions_dir() / f"session_{session_id}"

    review_request = {
        "session_id": session_id,
        "stage": meta.get("stage", "unknown"),
        "confidence": confidence,
        "status": meta.get("status"),
        "reason": meta.get("review_reason", "Below confidence threshold"),
        "flagged_at": now_iso(),
        "action_required": (
            "HUMAN_REVIEW_REQUIRED" if confidence < 0.6
            else "REVIEW_RECOMMENDED"
        ),
    }

    _atomic_write_json(session_dir / "review_request.json", review_request, dir=session_dir)

    # Also log to memory for persistence
    try:
        from uidetox.memory import add_note
        add_note(
            f"[LOW CONFIDENCE] Session {session_id} ({meta.get('stage')}): "
            f"confidence={confidence:.2f}. {meta.get('review_reason', '')}. "
            f"Action: {review_request['action_required']}"
        )
    except Exception:
        pass  # Non-critical


def get_pending_reviews() -> list[dict]:
    """Return all sessions flagged for human review."""
    sessions_dir = _sessions_dir()
    reviews = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        review_path = session_dir / "review_request.json"
        if review_path.exists():
            try:
                review = json.loads(review_path.read_text(encoding="utf-8"))
                reviews.append(review)
            except (json.JSONDecodeError, OSError):
                continue
    return reviews


def list_sessions() -> list[dict]:
    """Return all sessions with their metadata."""
    sessions_dir = _sessions_dir()
    results = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        meta_path = session_dir / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                results.append(meta)
            except (json.JSONDecodeError, OSError):
                continue
    return results


def get_session(session_id: str) -> dict | None:
    """Get full session details including prompt and result."""
    session_dir = _sessions_dir() / f"session_{session_id}"
    if not session_dir.exists():
        return None

    meta_path = session_dir / "meta.json"
    prompt_path = session_dir / "prompt.md"
    result_path = session_dir / "result.json"

    result = {}
    if meta_path.exists():
        result["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
    if prompt_path.exists():
        result["prompt"] = prompt_path.read_text(encoding="utf-8")
    if result_path.exists():
        result["result"] = json.loads(result_path.read_text(encoding="utf-8"))
    return result


def get_frontend_files(root: str = "") -> list[str]:
    """Return frontend source files under *root*, respecting IGNORE_DIRS."""
    frontend_exts = {".tsx", ".jsx", ".html", ".css", ".scss", ".vue", ".svelte", ".ts", ".js"}
    files = []

    if not root:
        try:
            from uidetox.state import get_project_root
            root = str(get_project_root())
        except Exception:
            root = "."
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith('.')]
        for filename in filenames:
            if Path(filename).suffix.lower() in frontend_exts:
                files.append(os.path.join(dirpath, filename))
    return sorted(files)


def _build_memory_block(query: str = "", files: list[str] | None = None) -> str:
    """Build a memory injection block from persistent agent memory.

    Injects learned patterns, notes, and session context so sub-agents
    have continuity with prior work. If a query is provided, performs
    a semantic search using ChromaDB. If files are provided, also injects
    targeted embedding-matched context for those specific files.
    """
    try:
        from uidetox.memory import (get_patterns, get_notes, get_session as get_mem_session,
                                     get_last_scan, build_targeted_context)
    except ImportError:
        return ""

    sections: list[str] = []

    patterns = get_patterns(query=query)
    if patterns:
        lines = ["## Learned Patterns (from prior sessions — MUST follow)"]
        for p in patterns[-15:]:  # Last 15 to keep prompt size manageable
            lines.append(f"- [{p.get('category', 'general')}] {p['pattern']}")
        sections.append("\n".join(lines))

    notes = get_notes(query=query)
    if notes:
        lines = ["## Agent Notes (persistent context)"]
        for n in notes[-10:]:
            lines.append(f"- {n['note']}")
        sections.append("\n".join(lines))

    session = get_mem_session()
    if session:
        lines = ["## Session Continuity"]
        lines.append(f"- Last Phase: {session.get('phase', 'unknown')}")
        lines.append(f"- Last Command: {session.get('last_command', 'none')}")
        if session.get("last_component"):
            lines.append(f"- Last Component: {session['last_component']}")
        lines.append(f"- Issues Fixed This Session: {session.get('issues_fixed_this_session', 0)}")
        if session.get("context"):
            lines.append(f"- Context: {session['context']}")
        sections.append("\n".join(lines))

    last_scan = get_last_scan()
    if last_scan:
        lines = ["## Last Scan Summary"]
        lines.append(f"- Total Found: {last_scan.get('total_found', 0)}")
        by_tier = last_scan.get("by_tier", {})
        if by_tier:
            tier_str = ", ".join(f"{k}: {v}" for k, v in sorted(by_tier.items()))
            lines.append(f"- By Tier: {tier_str}")
        top = last_scan.get("top_files", [])
        if top:
            lines.append(f"- Hottest Files: {', '.join(top[:5])}")
        sections.append("\n".join(lines))

    # ── Embedding-based targeted context (only if files provided) ──
    if files:
        try:
            targeted = build_targeted_context(files, issue_text=query)
            if targeted:
                sections.append(targeted)
        except Exception:
            pass  # ChromaDB optional — gracefully degrade

    if not sections:
        return ""

    return "\n\n".join(["# Memory Bank Injection"] + sections) + "\n"


def _build_deconfliction_block(shard_index: int, total_shards: int, shard_files: list[str]) -> str:
    """Build a deconfliction directive for parallel sub-agents.

    Prevents merge conflicts by ensuring each shard only touches its assigned files.
    """
    if total_shards <= 1:
        return ""

    return f"""## Shard Deconfliction (CRITICAL — violating this causes merge conflicts)
- You are shard {shard_index + 1} of {total_shards}.
- You may ONLY read and modify files in YOUR shard assignment below.
- Do NOT touch ANY file outside your shard, even if you see issues in it.
- If you discover issues in files outside your shard, note them but DO NOT fix.
- Your assigned files:
{chr(10).join(f'  - {f}' for f in shard_files)}
"""


def _has_fullstack(tooling: dict) -> bool:
    """Return True if the project has backend, database, or API layers detected."""
    return bool(
        tooling.get("backend") or tooling.get("database") or tooling.get("api")
    )


def _get_contract_artifacts(tooling: dict) -> dict[str, list[str]]:
    """Return normalized contract artifact paths with legacy fallbacks."""
    raw = tooling.get("contract_artifacts", {})
    schema_files: list[str] = []
    dto_files: list[str] = []
    contract_files: list[str] = []

    if isinstance(raw, dict):
        schema_files = [str(v) for v in raw.get("schema_files", []) if isinstance(v, str) and v]
        dto_files = [str(v) for v in raw.get("dto_files", []) if isinstance(v, str) and v]
        contract_files = [str(v) for v in raw.get("contract_files", []) if isinstance(v, str) and v]

    # Backward-compatible fallback for older tooling payloads.
    if not schema_files:
        for item in (tooling.get("database", []) or []):
            cfg = item.get("config_file")
            if isinstance(cfg, str) and cfg:
                schema_files.append(cfg)
        for item in (tooling.get("api", []) or []):
            cfg = item.get("config_file")
            if isinstance(cfg, str) and cfg:
                schema_files.append(cfg)

    # Stable ordering + dedupe
    schema_files = list(dict.fromkeys(schema_files))
    dto_files = list(dict.fromkeys(dto_files))
    contract_files = list(dict.fromkeys(contract_files))
    return {
        "schema_files": schema_files,
        "dto_files": dto_files,
        "contract_files": contract_files,
    }


def _build_tooling_block(tooling: dict) -> str:
    """Summarize detected stack details so sub-agents honor local conventions."""
    if not tooling:
        return ""

    lines = ["## Project Integration Profile"]
    package_manager = tooling.get("package_manager")
    if package_manager:
        lines.append(f"- Package manager: {package_manager}")

    typescript = tooling.get("typescript")
    if typescript:
        lines.append(f"- TypeScript: {typescript.get('config_file', 'detected')}")

    linter = tooling.get("linter")
    formatter = tooling.get("formatter")
    if linter or formatter:
        lines.append(
            "- Mechanical toolchain: "
            + ", ".join(
                part for part in [
                    f"lint={linter.get('name')}" if linter else "",
                    f"format={formatter.get('name')}" if formatter else "",
                ]
                if part
            )
        )

    for label in ("frontend", "backend", "database", "api"):
        items = tooling.get(label, []) or []
        if items:
            names = ", ".join(item.get("name", "unknown") for item in items)
            lines.append(f"- {label.capitalize()}: {names}")

    artifacts = _get_contract_artifacts(tooling)
    schema_count = len(artifacts.get("schema_files", []))
    dto_count = len(artifacts.get("dto_files", []))
    contract_count = len(artifacts.get("contract_files", []))
    if schema_count or dto_count or contract_count:
        lines.append(
            f"- Contract artifacts: schemas={schema_count}, dtos={dto_count}, contracts={contract_count}"
        )

    lines.append("- Preserve existing framework conventions, API contracts, DB schemas, and design tokens.")
    lines.append("- Prefer cohesive fixes that improve loading/error/empty states alongside the happy path.")
    return "\n".join(lines)


_DOMAIN_GITNEXUS_QUERIES: dict[str, list[str]] = {
    "typography": [
        'npx gitnexus query "font family weight size text heading"',
        'npx gitnexus query "typography type scale line-height tracking"',
    ],
    "color_contrast": [
        'npx gitnexus query "color palette theme accent neutral"',
        'npx gitnexus query "dark mode light contrast background"',
    ],
    "interaction_states": [
        'npx gitnexus query "hover focus active disabled loading error state"',
        'npx gitnexus query "button input form select checkbox toggle"',
    ],
    "content_ux_writing": [
        'npx gitnexus query "placeholder text label copy heading description"',
        'npx gitnexus query "error message toast alert notification"',
    ],
    "motion_animation": [
        'npx gitnexus query "animation transition motion delay duration easing"',
        'npx gitnexus query "keyframe transform opacity scale"',
    ],
    "spatial_layout": [
        'npx gitnexus query "grid flex layout container spacing gap padding margin"',
        'npx gitnexus query "responsive breakpoint media query mobile"',
    ],
    "materiality_surfaces": [
        'npx gitnexus query "shadow border radius opacity blur glassmorphism"',
        'npx gitnexus query "surface card panel overlay backdrop"',
    ],
    "consistency_system": [
        'npx gitnexus query "design token variable custom property theme"',
        'npx gitnexus query "component shared reusable import export default"',
    ],
    "identity_brand": [
        'npx gitnexus query "brand logo icon favicon hero landing"',
        'npx gitnexus query "image illustration asset avatar placeholder unsplash"',
    ],
    "architecture_responsive": [
        'npx gitnexus query "import export module component file structure"',
        'npx gitnexus query "fetch request API route endpoint handler"',
    ],
    "design_elegance": [
        'npx gitnexus query "design token variable custom property theme"',
        'npx gitnexus query "styling className tailwind css module styled"',
        'npx gitnexus query "layout spacing whitespace padding margin gap"',
    ],
    "accessibility": [
        'npx gitnexus query "aria label role landmark main nav header footer"',
        'npx gitnexus query "focus keyboard tabindex skip-to-content"',
        'npx gitnexus query "alt text img image picture srcset"',
    ],
    "api_data_coherence": [
        'npx gitnexus query "fetch request mutation query API endpoint"',
        'npx gitnexus query "DTO type interface response schema"',
        'npx gitnexus query "loading error empty state skeleton"',
        'npx gitnexus query "validation constraint required enum"',
    ],
    "performance_vitals": [
        'npx gitnexus query "lazy loading dynamic import code split"',
        'npx gitnexus query "image srcset picture WebP AVIF optimization"',
        'npx gitnexus query "memo callback useMemo useCallback performance"',
    ],
}

_GITNEXUS_REPO_SCOPED_SUBCOMMANDS = {
    "query",
    "context",
    "impact",
    "cypher",
    "detect_changes",
    "status",
    "analyze",
    "wiki",
}


def _inject_gitnexus_repo_flags(text: str, repo: str | None) -> str:
    """Inject `-r <repo>` into GitNexus CLI examples when repo is known."""
    repo_name = str(repo or "").strip()
    if not repo_name:
        return text

    lines: list[str] = []
    for line in text.splitlines():
        if "npx gitnexus " not in line:
            lines.append(line)
            continue
        if re.search(r"\s(?:-r|--repo)\b", line):
            lines.append(line)
            continue

        m = re.search(r"npx gitnexus\s+([a-zA-Z_]+)", line)
        if not m:
            lines.append(line)
            continue

        subcommand = m.group(1)
        if subcommand not in _GITNEXUS_REPO_SCOPED_SUBCOMMANDS:
            lines.append(line)
            continue

        replacement = f"npx gitnexus {subcommand} -r {shlex.quote(repo_name)}"
        lines.append(line[:m.start()] + replacement + line[m.end():])

    return "\n".join(lines)


def _build_domain_pre_review_block(domains: list[dict]) -> str:
    """Build a numbered pre-review analysis block with domain-specific GitNexus queries.

    Generates targeted GitNexus query commands based on the specific domains
    assigned to this review shard, so each shard gets queries relevant to
    its scoring focus rather than generic placeholders.
    """
    lines: list[str] = []
    step = 1
    lines.append(f"{step}. `npx gitnexus analyze` — refresh codebase index (skip if already fresh)")
    step += 1

    # Collect domain-specific queries (deduplicated)
    seen_queries: set[str] = set()
    for domain in domains:
        domain_name = domain.get("name", "")
        queries = _DOMAIN_GITNEXUS_QUERIES.get(domain_name, [])
        for query in queries:
            if query not in seen_queries:
                seen_queries.add(query)
                # Extract the concept from the query for the explanation
                domain_label = domain.get("label", domain_name)
                lines.append(f"{step}. `{query}` — map {domain_label.lower()} patterns")
                step += 1

    # Fallback: if no specific queries were found, use generic ones
    if not seen_queries:
        lines.append(f'{step}. `npx gitnexus query "design patterns"` — map relevant code patterns')
        step += 1
        lines.append(f'{step}. `npx gitnexus query "component structure"` — discover additional patterns')
        step += 1

    lines.append(f"{step}. `uidetox check --fix` — ensure code is clean before reviewing")
    step += 1
    lines.append(f"{step}. **Read every reference file listed below** — these contain the expert criteria")
    step += 1
    lines.append(f"{step}. Read every frontend file and evaluate ONLY your assigned domains")

    return "\n".join(lines)


# ── Issue-to-domain mapping for batch GitNexus queries ───────────

_ISSUE_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "typography": ["font", "text", "heading", "type", "line-height", "tracking", "weight", "serif", "sans"],
    "color_contrast": ["color", "contrast", "palette", "gradient", "dark", "light", "accent", "saturation", "hue"],
    "interaction_states": ["hover", "focus", "active", "disabled", "loading", "error", "state", "button", "input"],
    "content_ux_writing": ["copy", "lorem", "placeholder", "label", "message", "text", "content", "generic"],
    "motion_animation": ["animation", "transition", "motion", "bounce", "easing", "duration", "keyframe"],
    "spatial_layout": ["grid", "flex", "spacing", "padding", "margin", "layout", "container", "gap", "column"],
    "materiality_surfaces": ["shadow", "border", "radius", "blur", "glass", "surface", "card", "opacity"],
    "consistency_system": ["token", "variable", "consistent", "duplicate", "system", "convention"],
    "identity_brand": ["brand", "icon", "logo", "identity", "favicon", "hero", "unsplash", "image"],
    "architecture_responsive": ["responsive", "breakpoint", "mobile", "import", "semantic", "html", "div"],
    "design_elegance": ["cohesion", "aesthetic", "craft", "elegance", "harmony", "visual", "rhythm", "detail", "micro"],
    "accessibility": ["aria", "a11y", "screen reader", "landmark", "heading", "alt", "keyboard", "tab", "wcag", "lang"],
    "api_data_coherence": ["api", "fetch", "dto", "schema", "endpoint", "response", "cache", "mutation", "query", "data"],
    "performance_vitals": ["performance", "lazy", "bundle", "image", "optimize", "render", "vitals", "lcp", "cls", "split"],
}


def _derive_batch_gitnexus_queries(batch: list[dict]) -> str:
    """Derive GitNexus queries from issue descriptions in a fix batch.

    Analyzes the batch's issue text to determine which design domains
    are relevant, then emits targeted GitNexus commands for those domains.
    Also includes per-file context queries for the batch's target files.
    """
    # Determine which domains are relevant to this batch
    all_issue_text = " ".join(
        (i.get("issue", "") + " " + i.get("command", "")).lower()
        for i in batch
    )
    relevant_domains: set[str] = set()
    for domain_name, keywords in _ISSUE_DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in all_issue_text:
                relevant_domains.add(domain_name)
                break

    lines: list[str] = []
    step = 1

    # Per-file context queries
    batch_files = list(dict.fromkeys(i.get("file", "") for i in batch if i.get("file")))
    for bf in batch_files[:5]:
        fname = Path(bf).stem
        lines.append(f"{step}. `npx gitnexus context \"{fname}\"` — trace callers/callees for {fname}")
        step += 1
        lines.append(f"{step}. `npx gitnexus impact \"{fname}\"` — check blast radius before editing")
        step += 1

    # Domain-specific queries (deduplicated)
    seen_queries: set[str] = set()
    for domain_name in relevant_domains:
        queries = _DOMAIN_GITNEXUS_QUERIES.get(domain_name, [])
        for query in queries:
            if query not in seen_queries:
                seen_queries.add(query)
                lines.append(f"{step}. `{query}` — find related patterns")
                step += 1

    # Always include design token discovery
    token_query = 'npx gitnexus query "design token variable custom property theme"'
    if token_query not in seen_queries:
        lines.append(f"{step}. `{token_query}` — reuse existing design tokens")
        step += 1

    if not lines:
        lines.append(f'{step}. `npx gitnexus query "component design pattern"` — map relevant patterns')

    return "\n".join(lines)


def _build_frontend_gitnexus_block(phase: str = "general") -> str:
    """Build GitNexus analysis instructions for frontend-only projects.

    Unlike ``_build_fullstack_block`` which only emits content for full-stack
    projects, this provides GitNexus guidance for ALL projects — mapping
    component architecture, design patterns, state management, and coupling
    even when no backend/database/API layers are detected.
    """
    if phase == "observe":
        return """## GitNexus Codebase Intelligence (MANDATORY — run before observation)
1. `npx gitnexus analyze` — refresh codebase index
2. `npx gitnexus query "component page layout view route"` — map component architecture
3. `npx gitnexus query "shared hook context provider utility"` — map shared infrastructure
4. `npx gitnexus query "design token variable custom property"` — find design system surface
5. `npx gitnexus query "import export default dependency"` — map coupling and dependency chains
"""

    if phase == "diagnose":
        return """## GitNexus Pattern Discovery (MANDATORY — run before diagnosing)
1. `npx gitnexus query "design token variable theme color"` — find design system patterns
2. `npx gitnexus query "styling className tailwind css module"` — discover styling approaches
3. `npx gitnexus query "animation transition motion easing"` — find motion patterns
4. `npx gitnexus query "hover focus active disabled state"` — find interaction patterns
5. `npx gitnexus query "error loading empty skeleton"` — find state handling patterns
6. For each suspect component, run: `npx gitnexus context <component>` — trace callers/callees
"""

    if phase == "fix":
        return """## GitNexus Pre-Fix Analysis (MANDATORY — run BEFORE editing code)
1. `npx gitnexus context <component>` — trace ALL callers/callees before modifying
2. `npx gitnexus impact <symbol>` — check blast radius for any exports you'll change
3. `npx gitnexus query "design token variable theme"` — use existing design tokens, don't invent new ones
4. After fixing: `npx gitnexus detect_changes` — verify only expected files/symbols changed
"""

    if phase == "review":
        return """## GitNexus Pre-Review Analysis (MANDATORY — run BEFORE scoring)
1. `npx gitnexus analyze` — refresh codebase index
2. `npx gitnexus query "component page route layout view"` — map component graph
3. `npx gitnexus query "design token variable custom property"` — assess design system coverage
4. `npx gitnexus query "import export default dependency"` — check coupling and cohesion
5. `npx gitnexus query "shared hook context provider store"` — map state management
"""

    if phase == "verify":
        return """## GitNexus Post-Fix Verification (MANDATORY — run after fixes)
1. `npx gitnexus detect_changes` — verify only expected files/symbols changed
2. `npx gitnexus impact <modified_symbol>` — check blast radius for each modified export
3. `npx gitnexus context <component>` — verify component relationships are intact
"""

    return ""


def _build_fullstack_block(tooling: dict, phase: str = "general") -> str:
    """Build full-stack alignment instructions using GitNexus when backend/API/DB detected.

    Emits full-stack alignment instructions when backend/API/DB layers are
    detected.  For pure frontend projects, delegates to
    ``_build_frontend_gitnexus_block`` so every project gets GitNexus guidance.
    The *phase* parameter tailors instructions (observe, diagnose, fix, review, verify).
    """
    if not _has_fullstack(tooling):
        return _build_frontend_gitnexus_block(phase)

    backends = tooling.get("backend", []) or []
    databases = tooling.get("database", []) or []
    apis = tooling.get("api", []) or []
    artifacts = _get_contract_artifacts(tooling)

    stack_parts = []
    if backends:
        stack_parts.append(f"backend: {', '.join(b.get('name', '?') for b in backends)}")
    if databases:
        stack_parts.append(f"database: {', '.join(d.get('name', '?') for d in databases)}")
    if apis:
        stack_parts.append(f"API: {', '.join(a.get('name', '?') for a in apis)}")
    stack_summary = " | ".join(stack_parts)

    schema_files = artifacts.get("schema_files", [])
    dto_files = artifacts.get("dto_files", [])
    contract_files = artifacts.get("contract_files", [])

    def _render_artifacts(title: str, files: list[str]) -> str:
        if not files:
            return ""
        shown = files[:8]
        lines = "\n".join(f"  - `{f}`" for f in shown)
        suffix = ""
        if len(files) > len(shown):
            suffix = f"\n  - ... (+{len(files) - len(shown)} more)"
        return f"- {title}:\n{lines}{suffix}"

    artifact_sections = [
        _render_artifacts("Schema artifacts to read", schema_files),
        _render_artifacts("DTO artifacts to read", dto_files),
        _render_artifacts("Contract/validation artifacts to read", contract_files),
    ]
    schema_block = "\n".join(section for section in artifact_sections if section)
    if schema_block:
        schema_block = "\n" + schema_block

    if phase == "observe":
        return f"""## Full-Stack Integration (MANDATORY — {stack_summary})
This is a full-stack project. Frontend changes MUST be mapped against the backend.
{schema_block}

### GitNexus Full-Stack Mapping (run BEFORE observing frontend files)
1. `npx gitnexus query "API endpoint route handler"` — find all backend endpoints
2. `npx gitnexus query "DTO type interface schema"` — find data transfer types
3. `npx gitnexus query "database model entity table"` — find DB schema definitions
4. `npx gitnexus query "fetch request mutation query"` — find frontend data fetching
5. `npx gitnexus query "error handling validation"` — find error/validation patterns

### What to Map for Each Frontend Component
- Which API endpoint(s) does it call? (trace via gitnexus context)
- What DTO/response shape does it expect? Does the TS type match?
- What loading/error/empty states does the backend actually produce?
- Are form field names, validation rules, and constraints aligned with the DB schema?
- Are enum values, status codes, and nullable fields handled correctly?
"""

    if phase == "diagnose":
        return f"""## Full-Stack Alignment Audit (MANDATORY — {stack_summary})
{schema_block}

### GitNexus Cross-Layer Diagnosis (run ALL)
1. `npx gitnexus query "API endpoint route handler"` — map all backend endpoints
2. `npx gitnexus query "DTO type interface response"` — find backend response types
3. For each frontend data-fetching component:
   - `npx gitnexus context <component>` — trace its callers/callees across layers
   - Verify the frontend TypeScript type matches the backend DTO exactly
   - Check: nullable fields, optional properties, enum values, date formats
4. `npx gitnexus query "validation constraint required"` — find backend validation rules
   - Verify frontend form validation mirrors backend constraints
5. `npx gitnexus query "error status code exception"` — find backend error shapes
   - Verify frontend error states handle all backend error cases

### Full-Stack Issues to Detect (queue as T2 issues)
- Frontend type has fields the backend DTO doesn't send (phantom fields)
- Frontend assumes non-null but backend can return null/undefined
- Frontend form allows values the backend rejects (length, format, range)
- Frontend shows generic error but backend sends structured error codes
- Frontend caches stale data without revalidation strategy
- Frontend pagination/sort params don't match backend query API
- Frontend enums drift from backend/DB enum definitions
"""

    if phase == "fix":
        return f"""## Full-Stack Alignment (MANDATORY — {stack_summary})
{schema_block}

### BEFORE Fixing Any Component That Fetches Data
1. `npx gitnexus context <component>` — trace ALL cross-layer dependencies
2. `npx gitnexus impact <component> --direction upstream` — check blast radius
3. Read the backend endpoint code and DTO/response type it returns
4. Read the database schema/model to verify field constraints
5. Verify your fix preserves the data contract:
   - Response shape: field names, types, nullability must match
   - Error shape: status codes, error body structure must be handled
   - Validation: client-side rules must reflect server-side constraints
   - Pagination: page/limit/cursor params must match backend API

### Cross-Layer Fix Checklist
- [ ] Frontend types match backend DTOs field-for-field
- [ ] Loading states reflect actual backend latency patterns
- [ ] Error states handle all backend error codes (400, 401, 403, 404, 422, 500)
- [ ] Empty states match what the backend returns for zero-result queries
- [ ] Form validation mirrors backend validation rules
- [ ] Optimistic updates have proper rollback on server rejection
"""

    if phase == "review":
        return f"""## Full-Stack Alignment Scoring (MANDATORY — {stack_summary})
{schema_block}

### GitNexus Cross-Layer Review (run BEFORE scoring architecture)
1. `npx gitnexus query "API endpoint route handler"` — map backend surface
2. `npx gitnexus query "DTO type interface schema"` — find data contracts
3. `npx gitnexus query "fetch request mutation query"` — find frontend data calls
4. For 3-5 key data-fetching components:
   - `npx gitnexus context <component>` — verify cross-layer integrity
   - Check: does the frontend type match the backend response exactly?
   - Check: are error/loading/empty states reflecting real backend behavior?

### Architecture Scoring — Full-Stack Criteria
- DTO alignment: do frontend types match backend schemas field-for-field?
- Error surfacing: do API errors appear as meaningful, actionable UI feedback?
- Data flow: is fetching/caching/mutation coherent across the stack?
- Validation symmetry: do client-side rules mirror server-side constraints?
- State completeness: does every data-fetching surface handle loading/error/empty?
"""

    if phase == "verify":
        return f"""## Full-Stack Post-Fix Verification (MANDATORY — {stack_summary})
{schema_block}

### GitNexus Cross-Layer Verification (run ALL after fixes)
1. `npx gitnexus detect_changes` — verify changes only affect expected symbols/files
2. `npx gitnexus query "API endpoint route handler"` — confirm backend surface unchanged
3. `npx gitnexus query "DTO type interface schema"` — verify data contracts still match
4. For each modified component that fetches data:
   - `npx gitnexus impact <component> --direction upstream` — check blast radius
   - `npx gitnexus context <component>` — verify relationships intact
   - Confirm: frontend types still match backend DTOs after refactoring
   - Confirm: error/loading/empty states still reflect real backend behavior
5. `npx gitnexus query "validation constraint required"` — verify validation alignment preserved

### Post-Fix Full-Stack Checklist
- [ ] No new phantom fields introduced (frontend type has fields backend doesn't send)
- [ ] No broken data contracts (renamed/moved props still match API response shape)
- [ ] Error handling still covers all backend status codes
- [ ] Loading/empty states still match backend behavior patterns
- [ ] Form validation still mirrors server-side constraints
"""

    return ""


def generate_stage_prompt(stage: str, parallel: int = 1) -> list[str]:
    """Generate focused prompts for a specific sub-agent stage.

    If parallel > 1, chunks files or issues into non-overlapping buckets
    for massive AI swarm parallel execution.
    """
    state = load_state()
    config = load_config()
    parallel = _coerce_parallel(parallel)
    issues = state.get("issues", [])
    resolved = state.get("resolved", [])
    tooling = config.get("tooling", {})

    # Design dials — shared across all stage prompts
    variance = config.get("DESIGN_VARIANCE", 8)
    intensity = config.get("MOTION_INTENSITY", 6)
    density = config.get("VISUAL_DENSITY", 4)
    dials_block = f"""## Active Design Dials
- DESIGN_VARIANCE  = {variance}  {'(asymmetric, masonry, massive whitespace)' if variance > 7 else '(varied sizes, offset margins)' if variance > 4 else '(clean, centered, standard grids)'}
- MOTION_INTENSITY = {intensity}  {'(scroll-triggered, spring physics, magnetic)' if intensity > 7 else '(fade-ins, transitions, staggered entry)' if intensity > 5 else '(CSS hover/active only)'}
- VISUAL_DENSITY   = {density}  {'(cockpit mode, dense data)' if density > 7 else '(standard web app spacing)' if density > 3 else '(art gallery, spacious, luxury)'}

Use these dials to calibrate your decisions. Higher variance = more asymmetry required."""
    tooling_block = _build_tooling_block(tooling)
    gitnexus_repo = str(config.get("gitnexus_repo", "")).strip() or None

    def _finalize(prompts: list[str]) -> list[str]:
        return [_inject_gitnexus_repo_flags(prompt, gitnexus_repo) for prompt in prompts]

    if stage == "observe":
        if parallel > 1:
            files = get_frontend_files()
            if not files:
                memory_block = _build_memory_block()
                return _finalize([_observe_prompt(tooling_block, [], dials_block, memory_block, 0, 1)])
            # Workload-aware file sharding (size + issue density + coupling)
            chunks = _shard_items_by_workload(files, parallel, issues=issues)
            return _finalize([
                _observe_prompt(tooling_block, chunk, dials_block,
                                _build_memory_block(files=chunk), idx, len(chunks))
                for idx, chunk in enumerate(chunks)
            ])
        memory_block = _build_memory_block()
        return _finalize([_observe_prompt(tooling_block, [], dials_block, memory_block, 0, 1)])

    elif stage == "diagnose":
        return _finalize([_diagnose_prompt(issues, tooling_block, dials_block)])

    elif stage == "prioritize":
        return _finalize([_prioritize_prompt(issues)])

    elif stage == "fix":
        if not issues:
            return _finalize([_fix_prompt([], tooling_block, dials_block, 0, 1)])

        # Safely group by file to prevent merge conflicts
        grouped = {}
        for issue in issues:
            f = issue.get("file")
            if f not in grouped:
                grouped[f] = []
            grouped[f].append(issue)

        sorted_groups = sorted(grouped.values(), key=_issue_group_priority)

        # Take the most pressing file-groups to batch, up to parallel * 3
        top_groups = sorted_groups[: max(parallel * 3, parallel)]  # type: ignore
        group_shards = _shard_issue_groups_by_workload(top_groups, parallel)
        buckets = [[issue for group in shard for issue in group] for shard in group_shards]

        if not buckets:  # Fallback sanity check
            buckets = [issues[:5]] # type: ignore

        total_buckets = len(buckets)
        return _finalize([_fix_prompt(bucket, tooling_block, dials_block, idx, total_buckets) for idx, bucket in enumerate(buckets)])

    elif stage == "verify":
        return _finalize([_verify_prompt(issues, resolved, tooling_block)])

    elif stage == "review":
        files = get_frontend_files()
        if parallel > 1 and len(REVIEW_DOMAINS) > 1:
            domains = REVIEW_DOMAINS
            chunks = _shard_items(domains, min(parallel, len(domains)))
            # Keep domain shards (for rubric scoring) but pair each shard with
            # workload-balanced file slices so review load is not flat-count only.
            file_shards = _shard_items_by_workload(files, len(chunks), issues=issues) if files else [[] for _ in chunks]
            prompts = []
            for idx, domain_chunk in enumerate(chunks):
                shard_files = file_shards[idx] if idx < len(file_shards) else files
                prompts.append(
                    _review_domain_prompt(
                        domains=domain_chunk,
                        files=shard_files,
                        tooling_block=tooling_block,
                        dials_block=dials_block,
                        shard_index=idx,
                        total_shards=len(chunks),
                    )
                )
            return _finalize(prompts)
        return _finalize([_review_prompt(files, tooling_block, dials_block)])

    return _finalize([f"Unknown stage: {stage}"])


def _observe_prompt(tooling_block: str, files: list[str], dials_block: str,
                    memory_block: str = "", shard_index: int = 0, total_shards: int = 1) -> str:
    # Build file target list if specific shard provided
    target_directive = "Systematically scan the codebase and catalog everything you see."
    deconfliction = ""
    if files:
        file_list = "\n".join(f"- {f}" for f in files)
        target_directive = f"Systematically scan ONLY the following files in your shard:\n{file_list}"
        deconfliction = _build_deconfliction_block(shard_index, total_shards, files)

    config = load_config()
    tooling = config.get("tooling", {})
    fullstack_block = _build_fullstack_block(tooling, phase="observe")

    return f"""# UIdetox Sub-Agent: OBSERVE Stage

{memory_block}
{tooling_block}
{dials_block}
{deconfliction}
{fullstack_block}

## Your Mission
{target_directive} DO NOT fix anything yet.

## Tools Available
Use GitNexus to map codebase flows before deep diving!
- `npx gitnexus analyze` (refresh index — run first if stale)
- `npx gitnexus analyze --embeddings` (if embeddings are needed)
- `npx gitnexus query <concept>` (semantic search for code patterns)
- `npx gitnexus context <symbol>` (360-degree view of a symbol)
- `uidetox check --fix` (ensure code cleanliness during observation)

## What to Catalog
For every frontend file, note:
- **Design System Cohesion**: repeated tokens, inconsistent spacing/color/type decisions, variant drift
- **Typography**: Font families, sizes, weights, line heights, tracking
- **Colors**: All color values (hex, rgb, hsl, oklch, named, CSS variables, Tailwind classes)
- **Layout**: Grid systems, flex patterns, max-widths, padding/margin patterns, symmetry vs asymmetry
- **Components**: UI patterns used (cards, modals, heroes, navbars, forms, accordions, pricing tables)
- **Motion**: Animations, transitions, hover/focus/active effects, easing curves
- **States**: Loading, error, empty, disabled state handling
- **Accessibility**: ARIA labels, focus indicators, skip-to-content, lang attributes
- **Integration Boundaries**: data fetching surfaces, backend/API state mapping, schema/DTO assumptions
- **Content**: Placeholder data quality (names, numbers, dates, copy tone)

## Output Format
For each file, output a structured observation:
```
FILE: <path>
COHESION: <shared system patterns or inconsistencies>
TYPOGRAPHY: <what fonts/sizes you see>
COLORS: <what color values you see>
LAYOUT: <what layout patterns you see>
COMPONENTS: <what UI components you see>
MOTION: <what animations/transitions you see>
STATES: <what state handling you see>
ACCESSIBILITY: <what a11y features are present or missing>
INTEGRATION: <data/API/backend contract observations>
CONTENT: <quality of placeholder data and copy>
```

## Rules
- Be exhaustive. Miss nothing.
- Don't evaluate. Just observe and record.
- Include inline styles, CSS files, styled-components, Tailwind classes — everything.
"""


def _diagnose_prompt(issues: list, tooling_block: str, dials_block: str) -> str:
    existing = "\n".join(
        f"- [{i.get('tier')}] {i.get('file')}: {i.get('issue')}" for i in issues[:20] # type: ignore
    ) if issues else "None yet."

    config = load_config()
    tooling = config.get("tooling", {})
    fullstack_block = _build_fullstack_block(tooling, phase="diagnose")

    return f"""# UIdetox Sub-Agent: DIAGNOSE Stage

{tooling_block}
{dials_block}
{fullstack_block}

## Your Mission
Compare the observations from the OBSERVE stage against SKILL.md rules.
Identify every AI slop pattern and design violation.

## Pre-Diagnosis Analysis (MANDATORY)
1. `npx gitnexus query "design patterns"` — find design system usage and token consistency
2. `npx gitnexus query "styling color theme"` — discover color/theme patterns across components
3. `npx gitnexus query "animation transition motion"` — find motion patterns
4. `npx gitnexus query "hover focus active disabled state"` — find interaction state patterns
5. `npx gitnexus query "error loading empty skeleton placeholder"` — find state handling patterns
6. `npx gitnexus query "component page layout view"` — map component architecture
7. For EACH component with potential issues, run:
   `npx gitnexus context <component_name>` — understand callers/callees for integration issues
   `npx gitnexus impact <component_name>` — check blast radius before queuing fixes
8. `uidetox check --fix` — ensure code is clean before diagnosing

## Already Known Issues
{existing}

## Systematic Audit Checklist (check ALL categories)

### 1. Typography (consult reference/typography.md)
- Banned fonts: Inter, Roboto, Arial, Open Sans, system-ui as primary
- Missing type hierarchy (only Regular 400 and Bold 700 used)
- Serif fonts on dashboards
- Monospace as lazy "developer" vibe
- Large icons above every heading
- Hardcoded px font sizes instead of rem (accessibility)
- Overly tight leading/line-height on body paragraphs

### 2. Color & Contrast (consult reference/color-and-contrast.md)
- Purple-blue gradients (the #1 AI fingerprint)
- Cyan-on-dark palette
- Pure black (#000000)
- Gray text on colored backgrounds
- Gradient text on headings
- Oversaturated accents (> 80%)
- Neon/outer glows
- No dark mode support
- Raw CSS named colors (red, blue, green) instead of palette

### 3. Layout & Spacing (consult reference/spatial-design.md)
- Centered hero sections (banned when DESIGN_VARIANCE > 4)
- 3-column card feature rows
- h-screen instead of min-h-[100dvh]
- No max-width container
- Cards for everything / nested cards
- Uniform spacing everywhere
- Overpadded layouts
- Custom flex centering instead of grid place-items-center

### 4. Materiality & Surfaces
- Glassmorphism (backdrop-blur + transparency)
- Oversized border-radius (20-32px on everything)
- Oversized shadows (2xl/3xl)
- Pill-shaped badges
- Solid opaque borders for dividers (missing /50 opacity)

### 5. Motion & Interaction (consult reference/motion-design.md)
- Bounce/elastic easing
- animate-bounce/pulse/spin
- Missing hover, focus, active states
- Transform animations on nav links
- Hover states missing transition-all/colors

### 6. States & UX Completeness
- Missing loading states (or generic spinners instead of skeletons)
- Missing error states
- Missing empty states
- Missing disabled states
- Native browser scrollbars (missing custom styling/hiding)

### 7. Content & Data Quality
- Lorem Ipsum
- Generic names (John Doe, Jane Smith, Acme Corp)
- AI copy cliches (Elevate, Seamless, Unleash, Next-Gen)
- Round placeholder numbers (99.99%, 50%)
- Broken Unsplash links
- Emojis in UI

### 8. Code Quality & Semantics
- Div soup (no semantic HTML)
- Arbitrary z-index (9999)
- Inline styles mixed with classes
- Import hallucinations

### 9. Accessibility
- Missing focus indicators
- No ARIA labels on icon-only buttons
- Insufficient contrast ratios
- No skip-to-content link
- Labels missing htmlFor attributes linking to inputs

### 10. Strategic Omissions
- Missing 404 page
- Missing legal links
- Missing form validation
- Missing favicon
- Missing meta tags

### 11. Integration & Cohesion
- Components with inconsistent token usage across related flows
- API/loading/error/empty states that don't reflect actual backend behavior
- Frontend types that drift from DTOs, schemas, or ORM-backed constraints
- Screens that solve local issues but fragment the overall design language

## Output Format
For each issue found, output:
```
ISSUE: <description>
FILE: <path>
TIER: <T1|T2|T3|T4>
FIX: <what command or action to take>
```

Then run:
```
uidetox add-issue --file <path> --tier <tier> --issue "<description>" --fix-command "<cmd>"
```
"""


def _prioritize_prompt(issues: list) -> str:
    issue_list = "\n".join(
        f"- [{i.get('id')}] [{i.get('tier')}] {i.get('file')}: {i.get('issue')}" for i in issues
    ) if issues else "No issues in queue."

    return f"""# UIdetox Sub-Agent: PRIORITIZE Stage

## Your Mission
Review all queued issues and optimize the fix order for maximum impact with minimum risk.

## Current Queue
{issue_list}

## Prioritization Rules (from AGENTS.md)
1. Font swap — biggest instant improvement, lowest risk
2. Color palette cleanup — remove clashing or oversaturated colors
3. Hover and active states — makes the interface feel alive
4. Layout and spacing — proper grid, max-width, consistent padding
5. Replace generic components — swap cliché patterns for modern alternatives
6. Add loading, empty, and error states — makes it feel finished
7. Polish typography scale and spacing — the premium final touch

## Output
Provide the recommended fix order as a numbered list with rationale for each grouping.
"""


def _fix_prompt(batch: list, tooling_block: str, dials_block: str,
                shard_index: int = 0, total_shards: int = 1) -> str:
    if not batch:
        return "# No issues to fix. Run `uidetox scan` first."

    batch_text = "\n".join(
        f"- [{i.get('id')}] [{i.get('tier')}] {i.get('file')}: {i.get('issue')}" for i in batch
    )

    # Build inline context for the fix batch (same pattern as next.py)
    from uidetox.commands.next import SKILL_CONTEXT, _get_relevant_context # type: ignore
    contexts = _get_relevant_context(batch)
    context_block = ""
    if contexts:
        lines = ["## Relevant SKILL.md Design Rules"]
        for ctx, ref_file in contexts:
            lines.append(f"- {ctx}")
            if ref_file:
                lines.append(f"  (Deep-dive: {ref_file})")
        context_block = "\n".join(lines)

    # Build memory and deconfliction blocks with targeted embedding context
    batch_files = list(set(i.get("file", "") for i in batch))
    memory_block = _build_memory_block(query=batch_text, files=batch_files)
    deconfliction = _build_deconfliction_block(shard_index, total_shards, batch_files)

    config = load_config()
    tooling = config.get("tooling", {})
    fullstack_block = _build_fullstack_block(tooling, phase="fix")

    # Derive domain-specific GitNexus queries from the batch issues
    batch_gitnexus_queries = _derive_batch_gitnexus_queries(batch)

    return f"""# UIdetox Sub-Agent: FIX Stage

{memory_block}
{tooling_block}
{dials_block}
{deconfliction}
{fullstack_block}

## Your Mission
Fix the following {len(batch)} issues. Apply changes directly to the codebase.

## Issues to Fix
{batch_text}

{context_block}

## Pre-Fix GitNexus Analysis (MANDATORY — run BEFORE editing code)
{batch_gitnexus_queries}

## Tools & Rules
- Run `npx gitnexus analyze` first if index is stale
- Use `npx gitnexus impact <symbol>` BEFORE refactoring any exports
- Use `npx gitnexus context <symbol>` to understand component relationships
- Use `npx gitnexus query "design token variable theme"` to find existing tokens — reuse, don't reinvent
- Follow SKILL.md design rules for every change
- Fix ALL issues in one pass per component, then:
  1. Run `uidetox check --fix` to pass lint/format/typecheck BEFORE committing
  2. Run `npx gitnexus detect_changes` to verify only expected files/symbols changed
  3. Batch-resolve: `uidetox batch-resolve <ID1> <ID2> ... --note "what you changed"`
- Move to the next component immediately after resolving
"""


def _review_prompt(files: list[str], tooling_block: str, dials_block: str) -> str:
    """Single-agent comprehensive review prompt (non-parallel).

    Generates the full reference-driven scoring rubric with checklists,
    thresholds, and automatic deductions for consistent, thorough review.
    """
    file_list = "\n".join(f"- {f}" for f in files[:50]) if files else "- (scan codebase to discover)"

    config = load_config()
    tooling = config.get("tooling", {})
    fullstack_block = _build_fullstack_block(tooling, phase="review")

    # Build comprehensive domain rubric from REVIEW_DOMAINS
    domain_rubric_sections = []
    total_max = sum(d.get("max_score", 0) for d in REVIEW_DOMAINS)

    for domain in REVIEW_DOMAINS:
        max_s = domain.get("max_score", 0)
        refs = ", ".join(str(r) for r in domain.get("references", []))

        checklist = domain.get("checklist", [])
        checklist_block = ""
        if checklist:
            checklist_lines = "\n".join(f"      - [ ] {item}" for item in checklist)
            checklist_block = f"\n    **Verification Checklist**:\n{checklist_lines}"

        thresholds = domain.get("thresholds", {})
        thresholds_block = ""
        if thresholds:
            thresh_lines = "\n".join(f"      - {k}: **{v}**" for k, v in thresholds.items())
            thresholds_block = f"\n    **Hard Thresholds** (measure and cite):\n{thresh_lines}"

        deductions = domain.get("deductions", [])
        deductions_block = ""
        if deductions:
            ded_lines = "\n".join(f"      - {d}" for d in deductions)
            deductions_block = f"\n    **Automatic Deductions** (apply ALL that match):\n{ded_lines}"

        domain_rubric_sections.append(
            f"  ### {domain['label']} — {domain['rubric']}\n"
            f"    Focus: {domain['focus']}\n"
            f"    Reference: {refs}\n"
            f"    Max: {max_s} pts"
            f"{checklist_block}"
            f"{thresholds_block}"
            f"{deductions_block}\n"
        )

    domain_rubric = "\n".join(domain_rubric_sections)

    return f"""# UIdetox Sub-Agent: REVIEW Stage (Comprehensive)

{tooling_block}
{dials_block}
{fullstack_block}

## Your Mission
Perform a deep subjective quality review of the entire frontend codebase.
Score the design across ALL 10 domains ({total_max} total points). This is the most
critical scoring pass — the subjective score carries 70% weight in the final
blended Design Score.

## Scoring Protocol (MANDATORY — follow this exact process)
1. Start each domain at its max score
2. Walk through every checklist item — mark pass or fail
3. Measure every hard threshold — cite the actual value found
4. Apply every matching automatic deduction
5. The final domain score = max - sum(deductions), clamped to [0, max]
6. You MUST show your deduction math in the justification

## Pre-Review Analysis (MANDATORY — do ALL of these before scoring)
1. `npx gitnexus analyze` — refresh codebase index
2. `npx gitnexus query "frontend components"` — map the component graph
3. `npx gitnexus query "design patterns"` — find design system patterns
4. `npx gitnexus query "styling color theme"` — discover color/theme usage
5. `npx gitnexus query "animation transition motion"` — find motion patterns
6. `npx gitnexus query "error loading empty state"` — find state handling
7. `uidetox check --fix` — ensure code is clean before reviewing
8. `uidetox status` — see current score and queue state

## Files to Review
{file_list}

## Scoring Rubric — {total_max} Points Total (10 Domains)

{domain_rubric}

## Reference Files (MUST read before scoring — these are the authority)
- reference/typography.md, reference/spatial-design.md
- reference/color-and-contrast.md, reference/color-palettes.md
- reference/interaction-design.md, reference/motion-design.md
- reference/anti-patterns.md, reference/creative-arsenal.md
- reference/ux-writing.md, reference/responsive-design.md

## Scoring Guide (after applying domain rubrics)
     0-20  : Critical failures — AI slop everywhere, no design intention
    21-40  : Heavy AI fingerprints, generic template, multiple anti-patterns
    41-55  : Some design effort but obvious AI tells remain
    56-70  : Competent design with residual slop — checklist failures remain
    71-80  : Good design, mostly clean — some deductions still apply
    81-88  : Very good, intentional design — minor checklist gaps
    89-93  : Excellent — nearly all checklists pass, ≤2 minor deductions
    94-97  : Near-perfect — ALL checklists pass, ZERO pending issues
    98-100 : Flawless — zero deductions, perfection gate fully satisfied

## Post-Review Steps (MANDATORY)
1. Score each domain with full checklist/threshold/deduction justification
2. Sum domain scores for total (0-{total_max}, then normalize to 0-100)
3. Queue any new issues found during review:
   `uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"`
4. Run `uidetox check --fix` to ensure code cleanliness
5. Record your score: `uidetox review --score <TOTAL>`
6. Run `uidetox status` to see the blended Design Score

## Output Format
```
COMPREHENSIVE REVIEW:

{chr(10).join(f'[DOMAIN] {d["label"]}: <score>/{d.get("max_score", "?")}' for d in REVIEW_DOMAINS)}

CHECKLIST RESULTS:
  [domain_name] item_description: PASS | FAIL (evidence)
  ...

THRESHOLD MEASUREMENTS:
  [domain_name] threshold_name: measured_value vs required_value → PASS | FAIL
  ...

DEDUCTIONS APPLIED:
  [domain_name] deduction_rule: -N pts (evidence)
  ...

JUSTIFICATION:
  [domain_name]: Started at <max>. Deductions: <list>. Final: <score>/<max>.
  ...

RAW TOTAL: <sum>/{total_max}
NORMALIZED SCORE: <0-100>

CONFIDENCE: <0.0-1.0>
```
"""


def _review_domain_prompt(
    domains: list[dict],
    files: list[str],
    tooling_block: str,
    dials_block: str,
    shard_index: int,
    total_shards: int,
) -> str:
    """Domain-specific review prompt for parallel subjective analysis.

    Generates a comprehensive, reference-driven prompt with:
    - Full checklist items the reviewer must verify
    - Hard thresholds that must be measured and cited
    - Automatic deduction rules that prevent score inflation
    """
    domain_sections = []
    all_refs: list[str] = []
    total_max = 0

    has_arch_domain = False
    for domain in domains:
        refs = domain.get("references", [])
        all_refs.extend(refs)
        ref_list = ", ".join(str(r) for r in refs)
        max_s = domain.get("max_score", 0)
        total_max += max_s

        # Build checklist block
        checklist = domain.get("checklist", [])
        checklist_block = ""
        if checklist:
            checklist_lines = "\n".join(f"  - [ ] {item}" for item in checklist)
            checklist_block = f"\n- **Verification Checklist** (mark each pass/fail):\n{checklist_lines}"

        # Build thresholds block
        thresholds = domain.get("thresholds", {})
        thresholds_block = ""
        if thresholds:
            thresh_lines = "\n".join(f"  - {k}: **{v}**" for k, v in thresholds.items())
            thresholds_block = f"\n- **Hard Thresholds** (measure and cite):\n{thresh_lines}"

        # Build deductions block
        deductions = domain.get("deductions", [])
        deductions_block = ""
        if deductions:
            ded_lines = "\n".join(f"  - {d}" for d in deductions)
            deductions_block = f"\n- **Automatic Deductions** (apply ALL that match):\n{ded_lines}"

        domain_sections.append(
            f"### {domain['label']} — {domain['rubric']}\n"
            f"- **Focus**: {domain['focus']}\n"
            f"- **Reference**: {ref_list}\n"
            f"- **Max Score**: {max_s} pts\n"
            f"{checklist_block}"
            f"{thresholds_block}"
            f"{deductions_block}\n"
        )
        if "architecture" in domain.get("label", "").lower():
            has_arch_domain = True

    domain_block = "\n".join(domain_sections)
    file_list = "\n".join(f"- {f}" for f in files[:50]) if files else "- (scan codebase to discover)"
    ref_block = "\n".join(f"- {r}" for r in all_refs)

    config = load_config()
    tooling = config.get("tooling", {})
    fullstack_block = ""
    if has_arch_domain:
        fullstack_block = _build_fullstack_block(tooling, phase="review")

    return f"""# UIdetox Sub-Agent: REVIEW Stage (Domain Shard {shard_index + 1}/{total_shards})

{tooling_block}
{dials_block}
{fullstack_block}

## Your Mission
You are review shard {shard_index + 1} of {total_shards}. Perform a deep subjective
quality review ONLY for your assigned design domains. Score each domain precisely
using the rubric below. The subjective score carries 70% weight in the final
blended Design Score.

**Your shard total**: {total_max} pts across {len(domains)} domain(s).

## Scoring Protocol (MANDATORY — follow this exact process)
1. Start each domain at its max score
2. Walk through every checklist item — mark pass or fail
3. Measure every hard threshold — cite the actual value found
4. Apply every matching automatic deduction
5. The final domain score = max - sum(deductions), clamped to [0, max]
6. You MUST show your deduction math in the justification

## Pre-Review Analysis (MANDATORY — do ALL before scoring)
{_build_domain_pre_review_block(domains)}

## Your Assigned Domains (with full scoring criteria)
{domain_block}

## Files to Review
{file_list}

## Reference Files (MUST read before scoring — these are the authority)
{ref_block}

## Rules
- Score ONLY your assigned domains — do not score other domains
- Be rigorous: reference files are the source of truth for scoring
- **DO NOT inflate scores** — if you cannot verify a checklist item passes, it fails
- Use `npx gitnexus context <symbol>` to trace component relationships
- Queue any issues you find:
  `uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"`

## Post-Review Steps (MANDATORY)
1. Run `uidetox check --fix` after queuing issues
2. Output your partial scores with detailed justification

## Output Format
```
DOMAIN REVIEW (Shard {shard_index + 1}/{total_shards}):

{chr(10).join(f'[DOMAIN] {d["label"]}: <score>/{d.get("max_score", "?")}' for d in domains)}

CHECKLIST RESULTS:
  [domain_name] item_description: PASS | FAIL (evidence)
  ...

THRESHOLD MEASUREMENTS:
  [domain_name] threshold_name: measured_value vs required_value → PASS | FAIL
  ...

DEDUCTIONS APPLIED:
  [domain_name] deduction_rule: -N pts (evidence)
  ...

ISSUES FOUND: <count>

JUSTIFICATION:
  [domain_name]: Started at <max>. Deductions: <list>. Final: <score>/<max>.
  ...

PARTIAL_SCORE: <sum of domain scores>/{total_max}
CONFIDENCE: <0.0-1.0>
```
"""


def _verify_prompt(issues: list, resolved: list, tooling_block: str) -> str:
    # Check for pending reviews
    pending_reviews = get_pending_reviews()
    review_block = ""
    if pending_reviews:
        lines = ["## Pending Review Requests (from prior low-confidence sessions)"]
        for r in pending_reviews:
            lines.append(f"- Session {r['session_id']} ({r['stage']}): confidence={r['confidence']}, action={r['action_required']}")
        review_block = "\n".join(lines) + "\n"

    config = load_config()
    tooling = config.get("tooling", {})
    fullstack_block = _build_fullstack_block(tooling, phase="verify")

    return f"""# UIdetox Sub-Agent: VERIFY Stage

{review_block}
{tooling_block}
{fullstack_block}

## Your Mission
Re-scan the codebase to confirm improvements. Check that fixes actually improved the interface.

## Current State
- Pending issues: {len(issues)}
- Previously resolved: {len(resolved)}

## Verification Checklist
1. Run `npx gitnexus analyze` to refresh the codebase index after fixes
2. Run `npx gitnexus detect_changes` to verify changes only affect expected symbols
3. Run `npx gitnexus impact <modified_symbol>` for each modified export to check blast radius
4. Run `uidetox check --fix` to verify no build errors were introduced (tsc → lint → format)
5. Run `uidetox status` to check the current Design Score
6. Re-read every file that was modified during the FIX stage
7. Use `npx gitnexus context <component>` to verify component relationships are intact
8. Confirm the fixes match SKILL.md rules
9. Check for cascade effects (fixing one thing may reveal or create new issues)
10. If new issues are found, queue them: `uidetox add-issue --file <path> --tier <tier> --issue "<desc>" --fix-command "<cmd>"`
11. Run `uidetox status` again to see the updated score
12. Verify related flows still feel cohesive across loading, empty, error, and responsive states

## Confidence Scoring (MANDATORY)
You MUST yield a confidence score at the end of your output.

Rate your confidence on a 0.0 - 1.0 scale based on these criteria:

| Score Range | Meaning | Action |
|-------------|---------|--------|
| 0.95 - 1.0  | Highly confident — fixes are correct, no regressions | Auto-resolve |
| 0.85 - 0.94 | Confident — fixes look good, minor uncertainty | Auto-resolve |
| 0.70 - 0.84 | Moderate — some fixes may need adjustment | Flag for review, resolve with warnings |
| 0.50 - 0.69 | Low — significant uncertainty about fix quality | BLOCK resolution, require human review |
| 0.0 - 0.49  | Very low — fixes may have broken things | BLOCK resolution, revert recommended |

Consider these factors when scoring:
- Did `uidetox check --fix` pass without errors?
- Are there visual regressions (layout shifts, missing elements)?
- Did any fix introduce new anti-patterns?
- Were all cascade effects addressed?
- Is the design score trending upward?

## Output Format
```
VERIFICATION SUMMARY:
- Score before: <N>
- Score after: <N>
- Files verified: <list>
- New issues discovered: <count>
- Build status: PASS | FAIL
- Regressions found: <yes/no + details>

CONFIDENCE: <0.0 - 1.0>
RATIONALE: <1-2 sentence explanation of confidence level>
```

If CONFIDENCE < 0.85, explicitly list what needs human verification:
```
NEEDS_HUMAN_REVIEW:
- <specific concern 1>
- <specific concern 2>
```
"""
