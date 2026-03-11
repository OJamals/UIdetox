/**
 * UIdetox jscodeshift transform: Typography slop auto-fix
 *
 * Mechanically replaces T1-level typography anti-patterns:
 * - Generic AI fonts (Inter, Roboto, Arial) → distinctive typeface
 * - Hardcoded px font sizes → rem/Tailwind scale
 * - Tight line-height on body text → relaxed
 * - Viewport height → dynamic viewport height
 * - Generic animations → intentional transitions
 * - Verbose flex centering → grid place-items-center
 */
module.exports = function transformer(file, api) {
	const j = api.jscodeshift;
	const root = j(file.source);

	const replaceSlop = (val) => {
		return (
			val
				// Generic fonts → distinctive
				.replace(/\bfont-inter\b/g, "font-geist")
				.replace(/\bfont-sans\b/g, "font-geist")
				.replace(/\bfont-roboto\b/g, "font-geist")
				.replace(/\bfont-arial\b/gi, "font-geist")
				// Hardcoded px → rem/tailwind scale
				.replace(/\btext-\[\d+px\]/g, "text-sm")
				// Tight leading → relaxed (for body text contexts)
				.replace(/\bleading-none\b/g, "leading-relaxed")
				.replace(/\bleading-tight\b/g, "leading-normal")
				// Viewport height → dynamic viewport height
				.replace(/\bh-screen\b/g, "min-h-[100dvh]")
				// Generic Tailwind animations → proper transitions
				.replace(/\banimate-bounce\b/g, "transition-transform duration-200")
				.replace(/\banimate-pulse\b/g, "transition-opacity duration-300")
				.replace(/\banimate-spin\b/g, "animate-[spin_1s_linear_infinite]")
				// Verbose flex centering → grid
				.replace(
					/\bflex\s+justify-center\s+items-center\b/g,
					"grid place-items-center",
				)
				.replace(
					/\bflex\s+items-center\s+justify-center\b/g,
					"grid place-items-center",
				)
				// Clean double spaces
				.replace(/\s{2,}/g, " ")
				.trim()
		);
	};

	root.find(j.StringLiteral).forEach((path) => {
		if (typeof path.node.value === "string") {
			const newVal = replaceSlop(path.node.value);
			if (newVal !== path.node.value) {
				path.node.value = newVal;
			}
		}
	});

	root.find(j.TemplateElement).forEach((path) => {
		if (path.node.value?.raw) {
			const newVal = replaceSlop(path.node.value.raw);
			if (newVal !== path.node.value.raw) {
				path.node.value.raw = newVal;
				path.node.value.cooked = newVal;
			}
		}
	});

	return root.toSource();
};
