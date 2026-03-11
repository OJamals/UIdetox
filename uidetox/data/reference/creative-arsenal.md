# Creative Arsenal

Advanced design concepts for visually striking, memorable interfaces. Pull from this library to ensure output goes beyond generic UI.

---

## Navigation & Menus

### Mac OS Dock Magnification
Nav-bar at the edge; icons scale fluidly on hover, creating a playful proximity effect.

### Magnetic Button
Buttons that physically pull toward the cursor. **Performance note:** Use `useMotionValue` and `useTransform` — never `useState` for continuous hover tracking.

### Gooey Menu
Sub-items detach from the main button like viscous liquid using SVG filters for organic shapes.

### Dynamic Island
A pill-shaped UI component that morphs to show status, alerts, or mini-player content.

### Contextual Radial Menu
A circular menu expanding at exact click coordinates for context-sensitive actions.

### Floating Speed Dial
A FAB that springs out into a curved arc of secondary action buttons.

### Mega Menu Reveal
Full-screen dropdowns that stagger-fade complex navigation content.

---

## Layout & Grids

### Bento Grid
Asymmetric, tile-based grouping (like Apple Control Center). Mix 1×1, 2×1, 2×2, and 1×2 tiles.

### Masonry Layout
Staggered grid without fixed row heights (Pinterest-style). Elements fill vertical gaps organically.

### Chroma Grid
Grid borders or tiles that show subtle, continuously animating color gradients.

### Split Screen Scroll
Two screen halves sliding in opposite directions on scroll, creating parallax depth.

### Curtain Reveal
A hero section that parts in the middle like a curtain on scroll, revealing content beneath.

### Broken Grid / Asymmetry
Elements that deliberately ignore column structure — overlapping, bleeding off-screen, offset with calculated randomness.

---

## Cards & Containers

### Parallax Tilt Card
A 3D-tilting card tracking mouse coordinates for depth illusion.

### Spotlight Border Card
Card borders that illuminate dynamically under the cursor, following mouse position.

### Glassmorphism Panel (Done Right)
Beyond `backdrop-blur`: 1px inner border (`border-white/10`) + subtle inner shadow for physical edge refraction.

### Holographic Foil Card
Iridescent, rainbow light reflections that shift on hover, mimicking foil printing.

### Tinder Swipe Stack
A physical stack of cards the user can flick away, revealing the next.

### Morphing Modal
A button that seamlessly expands into its own full-screen dialog container via shared layout animation.

---

## Scroll Animations

### Sticky Scroll Stack
Cards that stick to the top and physically stack over each other during scroll.

### Horizontal Scroll Hijack
Vertical scroll translates into a smooth horizontal gallery pan with momentum.

### Locomotive Scroll Sequence
Video/3D frame sequences where playback is tied directly to scroll position.

### Zoom Parallax
A central background image zooming in/out seamlessly as the user scrolls.

### Scroll Progress Path
SVG vector lines or routes that draw themselves as the user scrolls down the page.

### Liquid Swipe Transition
Page transitions that wipe the screen like viscous liquid using SVG path morphing.

---

## Galleries & Media

### Dome Gallery
A 3D gallery environment feeling like a panoramic dome or curved wall.

### Coverflow Carousel
3D carousel with the center item focused and edge items angled back with perspective.

### Drag-to-Pan Grid
A boundless canvas grid the user can freely drag in any direction.

### Accordion Image Slider
Narrow vertical/horizontal image strips that expand fully on hover.

### Hover Image Trail
The cursor leaves a trail of popping/fading images that follow mouse movement.

### Glitch Effect Image
Brief RGB-channel shifting digital distortion triggered on hover.

---

## Typography & Text Effects

### Kinetic Marquee
Endless text bands that reverse direction or speed up on scroll interaction.

### Text Mask Reveal
Massive typography acting as a transparent window to video or animated imagery behind it.

### Text Scramble Effect
Matrix-style character decoding animation on load or hover.

### Circular Text Path
Text curved along a spinning circular SVG path.

### Gradient Stroke Animation
Outlined text with a gradient continuously running along the stroke.

### Kinetic Typography Grid
A grid of letters that dodge, rotate, or scatter away from the cursor.

### Variable Font Animation
Interpolate weight or width on scroll or hover for text that feels alive.

### Outlined-to-Fill Transitions
Text starts as a stroke outline and fills with color on scroll entry or interaction.

---

## Micro-Interactions & Effects

### Particle Explosion Button
CTAs that shatter into particles upon successful click.

### Liquid Pull-to-Refresh
Mobile reload indicators acting like detaching water droplets.

### Skeleton Shimmer
Shifting light reflections moving across placeholder loading boxes.

### Directional Hover Aware Button
Hover fill effect that enters from the exact side the mouse entered.

### Ripple Click Effect
Material Design-style visual waves rippling precisely from click coordinates.

### Animated SVG Line Drawing
Vectors that draw their own contours in real-time on page load.

### Mesh Gradient Background
Organic, lava-lamp-like animated color blobs for backgrounds.

### Lens Blur Depth
Dynamic focus blurring background UI layers to highlight a foreground action.

### Spotlight Borders
Card borders that illuminate dynamically following mouse position.

### Grain and Noise Overlays
A fixed, pointer-events-none overlay with subtle noise to break digital flatness.

---

## The Motion Engine (Bento 2.0)

For modern SaaS dashboards or feature sections, use these specific perpetual micro-animation archetypes:

### The Intelligent List
A vertical stack of items with an infinite auto-sorting loop. Items swap positions using `layoutId`, simulating AI prioritization.

### The Command Input
A search/AI bar with a multi-step typewriter effect. Cycles through prompts with blinking cursor and shimmering "processing" state.

### The Live Status
A scheduling interface with "breathing" status indicators. Pop-up notification badge emerges with overshoot spring, stays 3 seconds, vanishes.

### The Wide Data Stream
A horizontal infinite carousel of data cards. Seamless loop (`x: ["0%", "-100%"]`) with effortless speed.

### The Contextual UI (Focus Mode)
A document view that animates staggered text highlighting, followed by a float-in action toolbar.

---

## Implementation Rules

- **Never mix GSAP/ThreeJS with Framer Motion** in the same component tree
- Default to Framer Motion for UI/Bento interactions
- Use GSAP/ThreeJS exclusively for isolated full-page scrolltelling or canvas backgrounds
- Wrap all GSAP/ThreeJS in strict `useEffect` cleanup blocks
- **Performance:** Isolate perpetual animations in their own micro Client Components
- **Spring physics:** `type: "spring", stiffness: 100, damping: 20` for premium feel
- **No linear easing** — always spring or exponential deceleration
