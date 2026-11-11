# Verifying

**Verify with arithmetic, not with your eyes.** The frame's numbers come from the cached tree; the
DOM's come from one `measure()` call; `--diff` puts them side by side. Measure the blocks and the
gaps between them, **not the total height** — height is content-driven and will not match. This is
what "pixel perfect" is checked against; a screenshot is not.

## The protocol

1. Paste `scripts/measure.js` into the browser's JS tool. If the selectors are not known yet,
   call `inspect(rootSelector, 4)` **once** — an indented outline of the DOM under the root with
   each element's tag, id, classes, `data-slot`, box and leading text — and choose every selector
   from it. Then call `measure()` **once** with the root selector and a map of every Figma node id
   you care about to its CSS selector. Include the root itself so it reads `0,0`. It returns JSON:
   each target's box relative to the root, plus its computed padding, gap, radius, border, colours
   and typography.
2. Feed that JSON to `figma_fetch.py --diff <root node> -` in a heredoc. It lists only the values
   that differ, with the frame's number and the DOM's, and annotates the two Figma-vs-CSS
   differences below that are not defects. `--all` lists every row when you want the proof.
3. Fix what it lists, re-measure, re-diff. Two calls per round.

That is the entire loop. One `getBoundingClientRect` per node per turn is how a verification pass
runs to fifty turns; every one of them re-reads the whole conversation.

- **Set the viewport before measuring.** Width can read as 0 until the pane is sized, which silently
  fires mobile CSS and makes `getComputedStyle` lie.
- **A computed value is not proof the declaration applied.** `getComputedStyle` reports the *used*
  value for an absolutely positioned element, so a dropped `bottom` still reads as a number — it is
  just the static position. Check the emitted rule when a number looks plausible but wrong.
- **Read the rule body, not the class list.** Atomic CSS engines can emit a class with an empty `{ }`
  body, and no error, when they cannot resolve a token. Devtools shows the class present and
  everything looks wired. Walk `document.styleSheets` and check the rule declares anything.
- **Check the cascade layer order before blaming a selector.** Read the `@layer` statement off the
  document. When a framework's layers and the app's are interleaved, a rule can be correct, matched,
  and still lose.
- **To inspect something tiny**, clone it into a fixed overlay with `transform: scale(8)` and
  `transform-origin: top left`, then screenshot — browser screenshots are downscaled and small detail
  does not survive. For a hover-only element, set `style.opacity = "1"` first. **Reload afterwards**
  so a later screenshot is not stale.

## When the spec does not close

Figma is internally inconsistent in places — a value that differs between two variants of the same
component, a label copy-pasted across siblings, an icon that changes between states, a number that
cannot work. Implement the geometrically coherent version, and **say so in the report and the commit
message**. This is the *only* licence to depart from the frame, and it is conditional on saying so.
It is not cover for an estimate.

## Two differences that look like defects and are not

- **Figma trims its text boxes and CSS does not.** A label's box measures roughly 5px shorter per
  line in the frame than the same text does in the browser. Expect a block to run taller than the
  frame by about that much per line, and say so rather than shaving a gap to compensate.
- **Figma strokes a border inside the frame; CSS adds it outside.** A bordered element reads ~1px
  wide and a borderless one ~1px narrow against the same frame. Subtract 2px per bordered element and
  any residual is real. `box-shadow: inset 0 0 0 1px` paints the same pixel and moves nothing, which
  is the fix when an element positions anything against its own edge.
