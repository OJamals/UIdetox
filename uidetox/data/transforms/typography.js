module.exports = function transformer(file, api) {
  const j = api.jscodeshift;
  const root = j(file.source);

  const replaceSlop = (val) => {
    return val
      .replace(/\bfont-inter\b/g, 'font-geist')
      .replace(/\bfont-sans\b/g, 'font-geist')
      .replace(/\bfont-roboto\b/g, 'font-geist')
      .replace(/\btext-\[?\d+px\]?/g, 'text-sm')
      .replace(/\bleading-none\b/g, 'leading-relaxed')
      .replace(/\bleading-tight\b/g, 'leading-relaxed');
  };

  root.find(j.StringLiteral).forEach(path => {
    if (typeof path.node.value === 'string') {
      const newVal = replaceSlop(path.node.value);
      if (newVal !== path.node.value) {
        path.node.value = newVal;
      }
    }
  });
  
  root.find(j.TemplateElement).forEach(path => {
    if (path.node.value && path.node.value.raw) {
      const newVal = replaceSlop(path.node.value.raw);
      if (newVal !== path.node.value.raw) {
        path.node.value.raw = newVal;
        path.node.value.cooked = newVal;
      }
    }
  });

  return root.toSource();
};
