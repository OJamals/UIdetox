# Anti-Pattern Catalog

Consolidated list of banned AI UI patterns from UIdetox. These are the fingerprints of AI-generated work from 2024-2025.

**Rule:** If a UI choice feels like a default AI move, ban it and pick the harder, cleaner option.

---

## The AI Slop Test

If you showed this interface to someone and said "AI made this," would they believe you immediately? If yes, that's the problem. A distinctive interface should make someone ask "how was this made?"

---

## Visual & CSS

| Pattern | Why it's banned | Alternative |
|---------|----------------|-------------|
| Inter, Roboto, Arial, Open Sans font | Most common AI font choice | `Geist`, `Outfit`, `Cabinet Grotesk`, `Satoshi` |
| Purple-blue gradients | The #1 AI aesthetic fingerprint | Neutral bases + singular accent |
| Cyan-on-dark palette | AI "cool hacker" look | Tinted neutrals with considered accent |
| Neon accents on dark backgrounds | Looks "cool" without design decisions | Desaturated accents that blend with neutrals |
| Outer glows / box-shadow glows | Cheap depth illusion | Inner borders, tinted shadows |
| Pure `#000000` black | Never appears in nature | Off-black, zinc-950, tinted dark |
| Gradient text on headings | Decorative rather than meaningful | Solid color with intentional weight |
| Oversaturated accent colors (>80%) | Screams instead of blending | Desaturated accents |
| Bounce/elastic easing | Dated and tacky | ease-out-quart/quint/expo |
| Glassmorphism everywhere | Decoration not function | Reserved for intentional depth |
| Dark mode + glowing accents | Substitute for actual design | Commit to a real palette |
| Gray text on colored backgrounds | Washed out, low contrast | Shade of background color |
| Oversized border-radius (20-32px) | AI loves big rounded corners | 8-12px max for most elements |

## Layout & Spacing

| Pattern | Why it's banned | Alternative |
|---------|----------------|-------------|
| 3 equal card columns as feature row | Most generic AI layout | Zig-zag, asymmetric grid, masonry |
| Hero metric layout (big number + label) | Default AI dashboard | Content-specific density |
| Everything centered and symmetrical | Path of least resistance | Offset margins, mixed aspect ratios |
| `height: 100vh` for full sections | Broken on iOS Safari | `min-height: 100dvh` |
| No max-width container | Content stretches edge-to-edge | 1200-1440px container |
| Flexbox percentage math | Fragile, complex | CSS Grid |
| Cards for everything | Visual noise | Spacing, borders, negative space |
| Cards nested inside cards | Inception of noise | Flatten hierarchy |
| Identical card grids repeated | Templated look | Varied sizes and layouts |
| Everything overpadded | Looks wasteful | Reduce, create rhythm |
| Dashboard always has left sidebar | AI default | Top nav, command menu, collapsible panel |

## Component Patterns

| Pattern | Why it's banned | Alternative |
|---------|----------------|-------------|
| Pill-shaped "New"/"Beta" badges | Generic SaaS look | Square badges, flags, plain text |
| Accordion FAQ sections | Lazy information architecture | Side-by-side list, searchable help |
| 3-card carousel testimonials + dots | Template pattern | Masonry wall, embedded social |
| Pricing table with 3 towers | Every AI generates this | Highlight recommended with emphasis |
| Modals for everything | Lazy interaction design | Inline editing, slide-over panels |
| Avatar circles exclusively | Default AI | Squircles, rounded squares |
| Sun/moon dark mode toggle | Obvious default | Dropdown, system detection, settings |
| Footer link farm with 4 columns | Template footer | Simplified navigation + legal |
| KPI cards in a grid | Default dashboard layout | Inline metrics, contextual data |
| Lucide/Feather icons exclusively | AI's default icon set | Phosphor, Heroicons, custom |

## Typography

| Pattern | Why it's banned | Alternative |
|---------|----------------|-------------|
| Only Regular (400) and Bold (700) | No hierarchy subtlety | Medium (500), SemiBold (600) |
| Serif headline + sans body as "premium" | Shortcut, not design | Intentional pairing with character |
| Serif fonts on dashboards | Wrong context | High-end sans-serif |
| Monospace as lazy "developer" vibe | Cliché | Reserve for actual code/data |
| Oversized H1 that screams | Size ≠ hierarchy | Control with weight and color |
| All-caps subheaders everywhere | Template look | Sentence case, small-caps, italics |
| Large icons above every heading | Templated look | Remove or make contextual |

## Content & Data

| Pattern | Why it's banned | Alternative |
|---------|----------------|-------------|
| "John Doe", "Jane Smith" | Generic AI placeholder | Diverse, creative, realistic names |
| SVG "egg" / Lucide user avatars | Tells everyone it's generated | Photo placeholders, styled avatars |
| `99.99%`, `50%`, round numbers | Fake-feeling data | Organic: `47.2%`, `$1,287.34` |
| "Acme Corp", "Nexus", "SmartFlow" | Startup slop names | Premium, contextual brand names |
| "Elevate", "Seamless", "Unleash" | AI copywriting clichés | Concrete verbs, plain language |
| "Next-Gen", "Game-changer", "Delve" | More AI copy | Specific, honest language |
| "Oops!" error messages | False friendliness | Direct: "Connection failed." |
| Exclamation marks in success messages | Overly excited | Confident, not loud |
| Lorem Ipsum | Placeholder latin text | Real draft copy |
| Title Case On Every Header | Template formatting | Sentence case |
| Identical blog post dates | Lazy sample data | Randomized realistic dates |
| Same avatar for multiple users | Copy-paste error | Unique assets per person |

## Code Quality

| Pattern | Why it's banned | Alternative |
|---------|----------------|-------------|
| Div soup (`<div>` everywhere) | No semantic meaning | `<nav>`, `<main>`, `<article>`, `<aside>` |
| Inline styles mixed with classes | Inconsistent styling | Project's styling system |
| Hardcoded pixel widths | Inflexible | Relative units (%, rem, max-width) |
| Arbitrary z-index `9999` | No system | Clean z-index scale |
| Commented-out dead code | Debug artifacts | Remove before shipping |
| Import hallucinations | Packages not in dependencies | Check `package.json` first |
| Broken Unsplash links | Unreliable | `picsum.photos/seed/{name}/800/600` |
| Missing meta tags | SEO failure | title, description, og:image |
| Emojis in code/markup | Unprofessional | Icons (Phosphor, Radix) |

## Strategic Omissions (What AI Forgets)

These are things AI typically never generates. Include them:
- Legal links (privacy policy, terms) in footer
- "Back" navigation on inner pages
- Custom 404 page
- Form validation (client-side)
- "Skip to content" link for keyboard users
- Missing favicon
- Custom loading, empty, and error states
