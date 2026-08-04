---
name: audit
description: Perform comprehensive audit of interface quality across accessibility, performance, theming, and responsive design. Generates detailed report of issues with severity ratings and recommendations.
args:
  - name: area
    description: The feature or area to audit (optional)
    required: false
user-invokable: true
---

Run systematic quality checks and generate a comprehensive audit report with prioritized issues and actionable recommendations. Don't fix issues - document them for other commands to address.

**First**: Use the frontend-design skill for design principles and anti-patterns.

## Diagnostic Scan

Run comprehensive checks across multiple dimensions:

1. **Accessibility (A11y)** - Check for:
   - **Contrast issues**: Text contrast ratios < 4.5:1 (or 7:1 for AAA)
   - **Missing ARIA**: Interactive elements without proper roles, labels, or states
   - **Keyboard navigation**: Missing focus indicators, illogical tab order, keyboard traps
   - **Semantic HTML**: Improper heading hierarchy, missing landmarks, divs instead of buttons
   - **Alt text**: Missing or poor image descriptions
   - **Form issues**: Inputs without labels, poor error messaging, missing required indicators

2. **Performance** - Check for:
   - **Layout thrashing**: Reading/writing layout properties in loops
   - **Expensive animations**: Animating layout properties (width, height, top, left) instead of transform/opacity
   - **Missing optimization**: Incorrect image sizing/loading, excessive JS, or measured critical-path waste; avoid speculative `will-change`
   - **Bundle size**: Unnecessary imports, unused dependencies
   - **Render performance**: Profile unnecessary work before adding memoization
   - **User metrics**: LCP, INP, and CLS at the 75th percentile for relevant route/device segments

3. **Theming** - Check for:
   - **Hard-coded colors**: Colors not using design tokens
   - **Broken dark mode**: Missing variants or poor contrast when a dark theme is in product scope
   - **Inconsistent tokens**: Using wrong tokens, mixing token types
   - **Theme switching issues**: Values that don't update on theme change

4. **Responsive Design** - Check for:
   - **Fixed widths**: Hard-coded widths that break on mobile
   - **Target size**: Below 24×24 CSS pixels without a documented WCAG 2.5.8 exception; treat 44×44 as an enhanced aim
   - **Horizontal scroll**: Content overflow on narrow viewports
   - **Text scaling**: Layouts that break when text size increases
   - **Missing boundaries**: No content-driven adaptation where layout or tasks break

5. **Full-Stack Integration** - Check for:
   - **Contract drift**: UI request/response assumptions differ from API schemas, status codes, headers, auth, or DB constraints
   - **Failure semantics**: 401/403, validation, conflict, rate-limit, partial-success, offline, and retry behavior lack native UI states
   - **Mutation safety**: Optimistic rollback, idempotency, concurrency control, and cache invalidation are absent or unverified
   - **Observability**: User action, request, backend handler, and DB work cannot be correlated without exposing secrets or personal data

6. **Anti-Patterns** - Classify skill **DON'T** guidance as standards, measured risks, heuristics, or house style. Report AI-slop tells (generic gradients, glassmorphism, hero metrics, card grids, default typography) as design evidence, not automatic WCAG failures.

**CRITICAL**: This is an audit, not a fix. Document issues thoroughly with clear explanations of impact. Use other commands (normalize, optimize, harden, etc.) to fix issues after audit.

## Generate Comprehensive Report

Create a detailed audit report with the following structure:

### Anti-Patterns Verdict
**Start here.** Pass/fail: Does this look AI-generated? List specific tells from the skill's Anti-Patterns section. Be brutally honest.

### Executive Summary
- Total issues found (count by severity)
- Most critical issues (top 3-5)
- Overall quality score (if applicable)
- Recommended next steps

### Detailed Findings by Severity

For each issue, document:
- **Location**: Where the issue occurs (component, file, line)
- **Severity**: Critical / High / Medium / Low
- **Category**: Accessibility / Performance / Theming / Responsive
- **Description**: What the issue is
- **Impact**: How it affects users
- **WCAG/Standard**: Exact criterion or standard only when evidence proves a violation; otherwise mark heuristic or house style
- **Recommendation**: How to fix it
- **Suggested command**: Which command to use (prefer: {{available_commands}} — or other installed skills you're sure exist)

#### Critical Issues
[Issues that block core functionality or violate WCAG A]

#### High-Severity Issues  
[Significant usability/accessibility impact, WCAG AA violations]

#### Medium-Severity Issues
[Quality issues, WCAG AAA violations, performance concerns]

#### Low-Severity Issues
[Minor inconsistencies, optimization opportunities]

### Patterns & Systemic Issues

Identify recurring problems:
- "Hard-coded colors appear in 15+ components, should use design tokens"
- "Targets below 24×24 CSS pixels lack a verified WCAG 2.5.8 exception"
- "Missing focus indicators on all custom interactive components"

### Positive Findings

Note what's working well:
- Good practices to maintain
- Exemplary implementations to replicate elsewhere

### Recommendations by Priority

Create actionable plan:
1. **Immediate**: Critical blockers to fix first
2. **Short-term**: High-severity issues (this sprint)
3. **Medium-term**: Quality improvements (next sprint)
4. **Long-term**: Nice-to-haves and optimizations

### Suggested Commands for Fixes

Map issues to available commands. Prefer these: {{available_commands}}. You may also suggest other installed skills you're sure exist, but never invent commands.

Examples:
- "Use `/normalize` to align with design system (addresses N theming issues)"
- "Use `/optimize` to improve performance (addresses N performance issues)"
- "Use `/harden` to improve resilience (addresses N edge cases)"

**IMPORTANT**: Be thorough but actionable. Too many low-priority issues creates noise. Focus on what actually matters.

**NEVER**:
- Report issues without explaining impact (why does this matter?)
- Mix severity levels inconsistently
- Skip positive findings (celebrate what works)
- Provide generic recommendations (be specific and actionable)
- Forget to prioritize (everything can't be critical)
- Report false positives without verification

Remember: You're a quality auditor with exceptional attention to detail. Document systematically, prioritize ruthlessly, and provide clear paths to improvement. A good audit makes fixing easy.
