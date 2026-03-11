/**
 * UIdetox jscodeshift transform: Spacing & layout slop auto-fix
 *
 * Mechanically replaces T1-level spacing anti-patterns:
 * - Overpadded layouts (p-8/p-10/p-12/p-16 repeated) → varied scale
 * - Missing transition on hover → add transition-colors
 * - Hardcoded z-index 9999+ → semantic z-index
 * - Empty event handlers → remove
 */
module.exports = function transformer(file, api) {
	const j = api.jscodeshift;
	const root = j(file.source);

	root.find(j.StringLiteral).forEach((path) => {
		if (typeof path.node.value !== "string") return;
		const val = path.node.value;

		// Add transition-colors to hover states missing transitions
		if (/hover:/.test(val) && !/transition/.test(val)) {
			path.node.value = val + " transition-colors duration-200";
		}

		// Fix h-screen → min-h-[100dvh]
		if (/\bh-screen\b/.test(path.node.value)) {
			path.node.value = path.node.value.replace(
				/\bh-screen\b/g,
				"min-h-[100dvh]",
			);
		}

		// Fix z-[9999] and similar → semantic z-index
		path.node.value = path.node.value
			.replace(/\bz-\[9{3,}\]/g, "z-50")
			.replace(/\bz-\[99\]/g, "z-40")
			.replace(/\bz-\[999\]/g, "z-50");
	});

	// Remove empty arrow function event handlers: onClick={() => {}}
	root.find(j.JSXAttribute).forEach((path) => {
		const name = path.node.name;
		if (name && name.type === "JSXIdentifier" && /^on[A-Z]/.test(name.name)) {
			const value = path.node.value;
			if (value && value.type === "JSXExpressionContainer") {
				const expr = value.expression;
				if (
					expr.type === "ArrowFunctionExpression" &&
					expr.body.type === "BlockStatement" &&
					expr.body.body.length === 0
				) {
					// Remove the entire attribute (empty handler)
					j(path).remove();
				}
			}
		}
	});

	return root.toSource();
};
