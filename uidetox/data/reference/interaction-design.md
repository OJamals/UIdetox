# Interaction Design

## Applicable Interactive States

Design every state that a control's semantics and backend contract can actually enter. Do not invent loading/error/success states for a static link, or omit them from an async mutation:

| State | When | Visual Treatment |
|-------|------|------------------|
| **Default** | At rest | Base styling |
| **Hover** | Pointer over (not touch) | Subtle lift, color shift |
| **Focus** | Keyboard/programmatic focus | Visible ring (see below) |
| **Active** | Being pressed | Pressed in, darker |
| **Disabled** | Unavailable by contract | Distinct state plus reason/recovery where useful |
| **Loading** | Processing | Stable layout plus meaningful status/progress |
| **Error** | Invalid state | Red border, icon, message |
| **Success** | Completed | Green check, confirmation |

**The common miss**: Designing hover without focus, or vice versa. They're different. Keyboard users never see hover states.

## Focus Rings: Do Them Right

Never remove a visible focus indication without an equally visible replacement. `:focus-visible` can reduce pointer-only rings, but `:focus` is valid and lack of `:focus-visible` is not a failure:

```css
button:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}
```

**Focus ring design**:
- Clearly distinguishable from focused and unfocused adjacent colors
- Large and thick enough for product risk; test WCAG 2.4.7 and applicable enhanced criteria separately
- Use an inset or outset treatment with enough separation from adjacent colors and clipping boundaries
- Consistent across all interactive elements
- Not entirely hidden by sticky or overlay content during real keyboard traversal

## Form Design: The Non-Obvious

Placeholders are not persistent labels. Prefer visible labels and preserve an exact accessible-name association. Validate on submission, blur, or carefully designed inline feedback according to task risk; every-keystroke feedback can disrupt typing and IME composition. Put errors near their fields and connect them with `aria-describedby` or `aria-errormessage` as applicable.

## Loading States

Use optimistic updates only for reversible, conflict-aware operations with rollback or reconciliation evidence. Avoid them for payments, destructive actions, or security-sensitive changes. Choose skeletons for predictable content geometry, determinate progress for measurable work, and spinners for short indeterminate waits; announce meaningful status without stealing focus.

## Modals: The Inert Approach

Focus trapping in modals used to require complex JavaScript. Now use the `inert` attribute:

```html
<!-- When modal is open -->
<main inert>
  <!-- Content behind modal can't be focused or clicked -->
</main>
<dialog>
  <h2>Modal Title</h2>
  <!-- Open with showModal() for modal behavior -->
</dialog>
```

Or use the native `<dialog>` element:

```javascript
const dialog = document.querySelector('dialog');
dialog.showModal();  // Opens with focus trap, closes on Escape
```

## The Popover API

For tooltips, dropdowns, and non-modal overlays, use native popovers:

```html
<button popovertarget="menu">Open menu</button>
<div id="menu" popover>
  <button>Option 1</button>
  <button>Option 2</button>
</div>
```

**Benefits**: Browser-managed top-layer placement and optional light-dismiss. Authors still own accessible naming, semantics, focus behavior, and the widget's expected keyboard model.

## Destructive Actions: Undo > Confirm

Undo often outperforms routine confirmation dialogs, but only when backend semantics support safe compensation or delayed commitment. Use confirmation or review for irreversible, high-cost, legal/financial, security-sensitive, and batch actions. Preserve mutation idempotency, rollback, and conflict behavior.

## Keyboard Navigation Patterns

### Roving Tabindex

For component groups (tabs, menu items, radio groups), one item is tabbable; arrow keys move within:

```html
<div role="tablist">
  <button role="tab" tabindex="0">Tab 1</button>
  <button role="tab" tabindex="-1">Tab 2</button>
  <button role="tab" tabindex="-1">Tab 3</button>
</div>
```

Arrow keys move `tabindex="0"` between items. Tab moves to the next component entirely.

### Skip Links

When repeated blocks precede main content, provide a bypass such as `<a href="#main-content">Skip to main content</a>`. Hide it off-screen, then reveal it on focus.

### Scroll Snap

`scroll-snap-type: mandatory` can make content between non-adjacent snap points unreachable when content or viewports vary. Prefer `proximity` unless real keyboard, touch, zoom, and responsive tests prove every item remains reachable. Smooth scrolling is a separate motion choice and must not be added merely because snap is present.

## Gesture Discoverability

Swipe-to-delete and similar gestures are invisible. Hint at their existence:

- **Partially reveal**: Show delete button peeking from edge
- **Onboarding**: Coach marks on first use
- **Alternative**: Always provide a visible fallback (menu with "Delete")

Don't rely on gestures as the only way to perform actions.

---

**Avoid**: Removing focus indicators without alternatives. Using placeholder text as labels. Pointer targets below the WCAG 2.2 24×24 CSS pixel minimum without a valid spacing or other exception. Generic errors. Gesture-only actions. Custom controls without complete semantics and keyboard support. Aim for 44×44 CSS pixels where density and task context permit as an enhanced usability target.
