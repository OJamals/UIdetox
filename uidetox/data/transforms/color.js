module.exports = function transformer(file, api) {
  const j = api.jscodeshift;
  const root = j(file.source);

  const replaceSlop = (val) => {
    return val
      .replace(/\bbg-black\b/g, 'bg-zinc-950')
      .replace(/\btext-black\b/g, 'text-zinc-950')
      .replace(/#000000/g, '#0f0f0f')
      .replace(/\bbg-white\/[0-9]+\b/g, 'bg-white shadow-sm')
      .replace(/\bshadow-2xl\b/g, 'shadow-md')
      .replace(/\bshadow-3xl\b/g, 'shadow-md');
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
