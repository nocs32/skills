// measure.js — every number from the DOM in one browser call.
//
// Paste this whole file into the browser console (or the javascript tool), followed by ONE call:
//
//   measure('.invoice-card', {
//     '1:23': '.invoice-card',          // the frame root, so it reads 0,0
//     '1:30': '.invoice-card h2',
//     '1:44': '.invoice-card [data-slot=total]',
//   })
//
// Keys are Figma node ids, values are CSS selectors (first match wins). Every target is reported
// relative to the root selector's box, in CSS px, with the computed values the frame also carries.
// Hand the JSON it returns to:
//
//   python3 $FIGMA_FETCH --diff <root node> - <<'JSON'
//   { ...paste... }
//   JSON
//
// That is the whole verification round: one measure, one diff. Do not call getBoundingClientRect
// per node in separate turns — every extra turn re-reads the entire conversation.
//
// Do not know the selectors yet? ONE call to inspect() first:
//
//   inspect('.invoice-card', 4)
//
// prints the DOM under the root as an indented outline — tag, id, first classes, data-slot, box
// relative to the root, leading text — so every selector for measure() is chosen from one output
// instead of one outerHTML slice per turn.
function inspect(rootSel, depth = 4, limit = 160) {
  const root = document.querySelector(rootSel);
  if (!root) return `root selector matched nothing: ${rootSel}`;
  const rb = root.getBoundingClientRect();
  const r2 = (n) => Math.round(n * 100) / 100;
  const out = [];
  const walk = (el, d) => {
    if (out.length >= limit || d > depth) return;
    const b = el.getBoundingClientRect();
    const cls = [...el.classList].slice(0, 2).join('.');
    const text = [...el.childNodes].filter((n) => n.nodeType === 3)
      .map((n) => n.textContent.trim()).filter(Boolean).join(' ').slice(0, 24);
    out.push(`${'  '.repeat(d)}${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}` +
      `${cls ? '.' + cls : ''}${el.dataset.slot ? '[data-slot=' + el.dataset.slot + ']' : ''}` +
      ` [${r2(b.left - rb.left)},${r2(b.top - rb.top)} ${r2(b.width)}x${r2(b.height)}]` +
      `${text ? ' "' + text + '"' : ''}`);
    for (const c of el.children) walk(c, d + 1);
  };
  walk(root, 0);
  return out.join('\n') + (out.length >= limit ? '\n… (more; raise the limit or narrow the root)' : '');
}

function measure(rootSel, targets) {
  const hex = (c) => {
    const m = /rgba?\(([^)]+)\)/.exec(c || '');
    if (!m) return c || null;
    const [r, g, b, a] = m[1].split(',').map((s) => parseFloat(s));
    if (a === 0) return 'transparent';
    return '#' + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');
  };
  const px = (v) => {
    const n = parseFloat(v);
    return Number.isFinite(n) ? Math.round(n * 100) / 100 : null;
  };
  const r2 = (n) => Math.round(n * 100) / 100;

  const root = document.querySelector(rootSel);
  if (!root) return JSON.stringify({ error: `root selector matched nothing: ${rootSel}` });
  const rb = root.getBoundingClientRect();

  const one = (el) => {
    const b = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const bw = px(cs.borderTopWidth);
    return {
      x: r2(b.left - rb.left), y: r2(b.top - rb.top), w: r2(b.width), h: r2(b.height),
      paddingTop: px(cs.paddingTop), paddingRight: px(cs.paddingRight),
      paddingBottom: px(cs.paddingBottom), paddingLeft: px(cs.paddingLeft),
      rowGap: px(cs.rowGap), columnGap: px(cs.columnGap),
      borderRadius: px(cs.borderTopLeftRadius),
      // Figma's rectangleCornerRadii order: top-left, top-right, bottom-right, bottom-left.
      radii: [cs.borderTopLeftRadius, cs.borderTopRightRadius,
              cs.borderBottomRightRadius, cs.borderBottomLeftRadius].map(px),
      borderWidth: bw, borderColor: bw ? hex(cs.borderTopColor) : null,
      backgroundColor: hex(cs.backgroundColor), color: hex(cs.color),
      fontSize: px(cs.fontSize), fontWeight: px(cs.fontWeight),
      lineHeight: px(cs.lineHeight), letterSpacing: px(cs.letterSpacing),
      fontFamily: (cs.fontFamily || '').split(',')[0].replace(/["']/g, '').trim(),
      opacity: px(cs.opacity),
      display: cs.display, flexDirection: cs.display.includes('flex') ? cs.flexDirection : null,
    };
  };

  const out = {
    viewport: { w: innerWidth, h: innerHeight },
    root: Object.assign({ selector: rootSel }, one(root)),
    targets: {},
  };
  for (const [id, sel] of Object.entries(targets)) {
    const el = document.querySelector(sel);
    out.targets[id] = el ? Object.assign({ selector: sel }, one(el)) : null;
  }
  return JSON.stringify(out);
}
