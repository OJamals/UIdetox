# Accessibility and Inclusive Design

## Evidence Boundary

Treat [WCAG 2.2](https://www.w3.org/TR/WCAG22/) as normative accessibility baseline. Automated checks find evidence and risks; they do not prove full conformance. APG is informative, not a conformance standard or design system. Use native HTML first, then apply APG keyboard and focus patterns when building custom widgets.

Classify each recommendation:

- **Normative:** exact success criterion or platform contract.
- **Measured:** reproducible source or rendered evidence with provenance.
- **Heuristic:** review signal requiring confirmation.
- **House style:** UIdetox anti-slop preference, overridable by project intent.

Never relabel heuristic or taste preference as a WCAG failure.

## WCAG 2.2 Additions

Audit every applicable WCAG 2.2 criterion, including:

- **Focus Not Obscured (2.4.11, AA):** author-created sticky surfaces, banners, drawers, and persistent overlays must not entirely hide focused controls. Test real keyboard traversal at each required viewport.
- **Dragging Movements (2.5.7, AA):** every drag operation needs a non-dragging pointer alternative unless dragging is essential or user-agent controlled.
- **Target Size Minimum (2.5.8, AA):** pointer targets are at least 24×24 CSS pixels or meet the spacing exception, equivalent-control, inline, user-agent, or essential exception. Preserve evidence for any exception.
- **Target Size Enhanced (2.5.5, AAA):** 44×44 CSS pixels is a stronger target and useful motor-accessibility aim, not Level AA minimum.
- **Consistent Help (3.2.6, A):** repeated help mechanisms remain in same relative order across same page variation.
- **Redundant Entry (3.3.7, A):** do not require users to re-enter information already supplied in same process unless an exception applies.
- **Accessible Authentication (3.3.8, AA):** do not require cognitive-function tests without an alternative, assistance, or recognized-object/personal-content exception. Support password managers and paste.

Use [W3C WCAG 2.2 overview](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/) and criterion-specific Understanding documents when recording exact exceptions.

## Focus and Keyboard

- Keep visible focus for every keyboard-operable control. Custom :focus-visible treatment is optional; :focus is valid. Failure is missing, imperceptible, or obscured focus—not selector choice.
- Preserve natural tab order. Positive tabindex is usually wrong; composite widgets should use keyboard model appropriate to their role.
- Keep focus and selection visually distinct.
- Move focus only when interaction context requires it, such as opening a modal or completing a route transition.
- Use skip links or another bypass mechanism when repeated blocks precede main content.
- Test opening, closing, Escape, restoration, and background inertness for modal dialogs.

References: [WAI keyboard interface guidance](https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/) and [Focus Not Obscured](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum).

## Names, Structure, and Status

- Prefer native elements and persistent visible labels. Associate controls programmatically using for/htmlFor, nesting, aria-labelledby, or another valid accessible-name path.
- Headings must describe and reflect document structure. One clear page-level h1 is a useful default, not a universal WCAG single-heading rule.
- Label repeated landmarks distinctly.
- Do not add ARIA that conflicts with native semantics.
- `aria-disabled="true"` exposes state but does not suppress activation or apply native disabled behavior. Prefer native `disabled` where appropriate; custom controls must block pointer and keyboard activation while disabled.
- For sortable tables, put `aria-sort` on the currently sorted column header and update or move it when sort changes. A button inside each sortable header exposes the action; do not mark every unsorted header with a false current state.
- Announce non-focus-changing results, errors, waiting, and progress with an appropriate live-region role. Use role="status" for polite status updates; reserve role="alert" or assertive announcements for urgent, time-sensitive information.
- Avoid chatty live regions. Existing widget state changes may already be announced through name, role, and value.

References: [W3C status-message guidance](https://www.w3.org/WAI/WCAG22/Understanding/status-messages) and [WAI page-structure headings](https://www.w3.org/WAI/tutorials/page-structure/headings/).

## Forms and Error Recovery

- Give instructions before input when format, units, requirements, or consequences are not obvious.
- Preserve autocomplete tokens, password-manager support, paste, and platform input behavior.
- Validate at a useful moment: submission, blur, or carefully designed inline feedback. Do not make every keystroke noisy.
- Identify each error in text, associate it with field, retain user input, and focus a summary only when that improves recovery.
- Suggest corrections when known and safe.
- For legal, financial, destructive, or data-changing submissions, provide review, confirmation, reversal, or correction as required.
- Avoid redundant entry across a flow. Prepopulate or offer selection of previously entered values when allowed.

## Visual Adaptation

Test instead of prescribing one palette or font:

- text and non-text contrast in default, hover, focus, active, disabled, selected, error, and high-contrast states;
- 200% text resize, 400% reflow where applicable, user text-spacing overrides, and browser zoom;
- Windows forced colors and user contrast preferences without suppressing meaningful indicators;
- reduced motion without removing necessary state feedback;
- light/dark color schemes without assuming dark mode is mandatory;
- font loading, fallback metrics, missing glyphs, localization expansion, and clipping.

Do not hide native scrollbars by default. Scroll regions need a discoverable indicator, keyboard access when interactive, and visible overflow behavior.

## Input Modalities and Gestures

Screen size does not identify input method. Test keyboard, mouse, touch, pen, switch/voice paths, and mixed devices.

- Gate hover-only polish with hover capability; never make hover the only way to discover or operate a control.
- Use passive listeners only when handler never needs preventDefault().
- Offer visible alternatives to swipes, drags, long presses, and precision gestures.
- Preserve platform conventions and avoid custom controls unless complete semantics and keyboard model are proven.

## Internationalization

- Declare page language and language changes.
- Set dir="rtl" for right-to-left documents; use dir="auto" or bdi for unknown user-generated direction.
- Prefer CSS logical properties so layout mirrors by writing direction.
- Test long translations, plurals, grammatical variation, mixed scripts, localized numbers/dates/currency, time zones, and non-Gregorian expectations where relevant.
- Preserve IME composition: do not submit, validate, or trigger shortcuts from intermediate composition events.
- Never assume string length equals visible width or user-perceived characters.

Reference: [W3C structural RTL guidance](https://www.w3.org/International/questions/qa-html-dir).

## Verification Matrix

For every critical flow, record:

- route, user state, data state, viewport, input modality, locale/direction, color preference, motion preference, zoom/text spacing;
- source owner plus backend/API/DB contract anchors;
- expected accessible name, role, value, focus order, status announcement, and recovery path;
- before/after evidence only after a real source change;
- no-op evidence showing identical captures when source and environment are unchanged.
