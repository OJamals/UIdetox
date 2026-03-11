---
name: scan
description: Full diagnostic audit of frontend interface quality. Produces a prioritized issue list with tiered severity. Run this first to understand what needs fixing.
args:
  - name: target
    description: File, component, or area to scan (optional — scans everything if omitted)
    required: false
---

Run a full diagnostic scan and generate a prioritized issue list. This is Phase 1 of the UIdetox loop.

**First**: Read and apply the full SKILL.md for design principles, anti-patterns, and engineering rules.

## Scan Dimensions

Analyze every frontend file in scope across these dimensions:

### 1. AI Slop Detection (CRITICAL — do this first)
Does this look like every other AI-generated interface from 2024-2025? Check against ALL banned patterns in SKILL.md Section 4 (Anti-Pattern Catalog):
- AI color palette (purple-blue gradients, cyan-on-dark, neon accents)
- Generic fonts (Inter, Roboto, Arial, system defaults)
- Identical card grids, hero metric layouts
- Glassmorphism, outer glows, gradient text
- Bounce/elastic easing
- Generic startup copy and fake data

### 2. Typography
- Browser default fonts or Inter everywhere?
- Headlines lack presence (too small, no tracking, no weight variation)?
- Body text too wide (>65 characters per line)?
- Only Regular and Bold weights used?
- Numbers in proportional font instead of tabular?
- Missing letter-spacing adjustments?

### 3. Color & Surfaces
- Pure `#000000` background?
- Oversaturated accent colors (saturation >80%)?
- More than one accent color?
- Mixing warm and cool grays?
- Gray text on colored backgrounds?
- Generic box-shadow (not tinted to background)?
- Flat design with zero texture?

### 4. Layout & Spacing
- Everything centered and symmetrical?
- Three equal card columns as feature row?
- Using `height: 100vh` instead of `min-height: 100dvh`?
- No max-width container?
- Complex flexbox percentage math instead of CSS Grid?
- Cards used where spacing/borders would suffice?

### 5. Interactivity & States
- Missing hover states on buttons?
- No active/pressed feedback?
- No focus indicators for keyboard navigation?
- No loading states (or generic circular spinners)?
- No empty states?
- No error states?
- Instant transitions (zero duration)?

### 6. Responsiveness
- Fixed widths that break on mobile?
- Touch targets <44x44px?
- Horizontal scroll on narrow viewports?
- No mobile/tablet breakpoints?

### 7. Accessibility
- Contrast ratios <4.5:1?
- Missing ARIA labels?
- No semantic HTML (div soup)?
- Missing alt text on images?

### 8. Code Quality
- Div soup instead of semantic elements?
- Inline styles mixed with CSS classes?
- Hardcoded pixel widths?
- Import hallucinations (importing packages not in package.json)?
- Console.log or commented-out code?

## Output Format

### AI Slop Verdict
Pass/fail: Does this look AI-generated? List specific tells. Be brutally honest.

### Issue List (sorted by tier)

For each issue:
- **ID**: `SCAN-001`, `SCAN-002`, etc.
- **Tier**: T1 (quick fix) / T2 (targeted refactor) / T3 (design judgment) / T4 (major redesign)
- **Category**: Typography / Color / Layout / Interactivity / Responsive / A11y / Code / Anti-Pattern
- **Location**: File, component, line number
- **Issue**: What's wrong
- **Impact**: Why it matters
- **Fix**: Specific recommendation
- **Command**: Which UIdetox command to use (`/normalize`, `/colorize`, `/animate`, etc.)

### Summary Statistics
- Total issues by tier (T1: N, T2: N, T3: N, T4: N)
- Recommended fix order (from SKILL.md Section 7)
- Estimated effort

**CRITICAL**: Be thorough but actionable. This report drives the entire fix loop.
