/**
 * UIdetox jscodeshift transform: Color slop auto-fix
 *
 * Mechanically replaces T1-level color anti-patterns:
 * - Pure black (#000000, bg-black, text-black) → tinted dark neutrals
 * - Glassmorphism opacity patterns → solid surfaces
 * - Oversized shadows → subtle shadows
 * - Neon glow shadows → clean shadows
 * - Raw CSS named colors → proper palette tokens
 * - Gradient text (bg-clip-text) → solid color
 */
module.exports = function transformer(file, api) {
	const j = api.jscodeshift;
	const root = j(file.source);

	const replaceSlop = (val) => {
		return (
			val
				// Pure black → tinted dark neutrals
				.replace(/\bbg-black\b/g, "bg-zinc-950")
				.replace(/\btext-black\b/g, "text-zinc-950")
				.replace(/\bborder-black\b/g, "border-zinc-900")
				.replace(/#000000/g, "#0f0f0f")
				.replace(/#000\b/g, "#0f0f0f")
				// Glassmorphism → solid surfaces
				.replace(/\bbackdrop-blur-(?:sm|md|lg|xl|2xl|3xl)\b/g, "")
				.replace(/\bbg-white\/[0-9]+\b/g, "bg-white shadow-sm")
				// Oversized shadows → subtle
				.replace(/\bshadow-2xl\b/g, "shadow-md")
				.replace(/\bshadow-3xl\b/g, "shadow-md")
				// Neon glow → clean shadow
				.replace(/\bshadow-glow\b/g, "shadow-sm")
				.replace(/\bshadow-neon\b/g, "shadow-sm")
				// Gradient text → solid
				.replace(/\bbg-clip-text\b/g, "")
				.replace(/\btext-transparent\b/g, "")
				// Oversized radii → tighter
				.replace(/\brounded-3xl\b/g, "rounded-xl")
				.replace(/\brounded-2xl\b(?!\s*(?:md:|lg:|xl:))/g, "rounded-lg")
				// Opaque borders → subtle opacity
				.replace(/\bborder-gray-200\b(?!\/)/g, "border-gray-200/50")
				.replace(/\bborder-gray-300\b(?!\/)/g, "border-gray-200/50")
				.replace(/\bborder-gray-700\b(?!\/)/g, "border-gray-700/50")
				.replace(/\bborder-gray-800\b(?!\/)/g, "border-gray-700/50")
				// Clean up double spaces from removals
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
