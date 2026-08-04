/**
 * UIdetox jscodeshift transform: exact EMPTY_HANDLER remediation.
 *
 * Removes only no-argument, empty JSX event-handler arrow functions. The
 * detector and transform recognize the same syntax; no category-level edits.
 */
module.exports = function transformer(file, api) {
	const j = api.jscodeshift;
	const root = j(file.source);

	root.find(j.JSXAttribute).forEach((path) => {
		const name = path.node.name;
		if (name?.type !== "JSXIdentifier" || !/^on[A-Z]/.test(name.name)) return;
		const value = path.node.value;
		if (value?.type !== "JSXExpressionContainer") return;
		const expression = value.expression;
		if (
			expression.type === "ArrowFunctionExpression" &&
			expression.params.length === 0 &&
			expression.body.type === "BlockStatement" &&
			expression.body.body.length === 0
		) {
			j(path).remove();
		}
	});

	return root.toSource();
};
