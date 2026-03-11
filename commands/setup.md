---
name: setup
description: Gather project design context, discover existing design systems, and configure UIdetox dials for the project.
args:
  - name: none
    description: No arguments — runs interactive setup
    required: false
---

Gather project context and configure UIdetox for this specific codebase. Run this once per project before scanning.

## Discovery

### 1. Detect Tech Stack
- **Framework**: React, Next.js, Vue, Svelte, Astro, vanilla HTML?
- **Styling**: Tailwind (v3/v4?), CSS Modules, styled-components, vanilla CSS?
- **Component library**: shadcn/ui, Radix, MUI, Ant Design, custom?
- **Animation library**: Framer Motion, GSAP, CSS-only?
- **Icons**: Phosphor, Radix, Lucide, Heroicons, custom?

Read `package.json` and key config files to determine the stack.

### 2. Discover Design System
Search for existing design tokens, guidelines, or style docs:
- `design-system`, `ui-guide`, `style-guide` directories
- CSS custom properties / design tokens
- Theme configuration files
- Brand guidelines or color palettes
- Typography configuration

### 3. Assess Current State
Quick scan for:
- Primary fonts in use
- Color palette in use
- Component patterns
- Current design quality level (rough estimate)

## Configure

Based on discovery, recommend dial settings:

### DESIGN_VARIANCE (1-10)
- Marketing/landing pages: 6-9
- SaaS dashboards: 3-6
- Data-heavy tools: 2-4
- Creative portfolios: 7-10
- Enterprise/corporate: 3-5

### MOTION_INTENSITY (1-10)
- Simple informational sites: 2-4
- Marketing pages: 5-8
- Interactive apps: 4-7
- Data dashboards: 2-4
- Creative showcases: 7-10

### VISUAL_DENSITY (1-10)
- Landing pages: 2-4
- Standard web apps: 4-6
- Admin panels: 5-7
- Data dashboards: 7-9
- Art/portfolio: 1-3

## Output

Report:
1. **Stack detected**: Framework, styling, libraries
2. **Design system found**: Existing tokens, colors, typography, or "none"
3. **Current quality**: Brief assessment of AI slop level
4. **Recommended dials**: DESIGN_VARIANCE, MOTION_INTENSITY, VISUAL_DENSITY with rationale
5. **Ready to scan**: Confirm configuration and suggest running `/scan`
