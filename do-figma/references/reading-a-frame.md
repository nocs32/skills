# Reading a frame

## Which field answers which question

- **`absoluteBoundingBox`** — layout maths. Rotation is already baked in, so a rotated node's
  numbers are the visual ones.
- **`absoluteRenderBounds`** — what is *painted*. Includes shadow spread and stroke width, so a
  384px card with a drop shadow renders 441 wide. **Never subtract that overhang from a layout
  number** — it is the shadow, not the box.
- **`minHeight` beside `height`** — a stated constraint next to a computed size. They differ, and
  the difference is meaningful.
- **`visible: false`** — a hidden variant. Measuring one is a silent, total waste of a round.
- **`overrides` / `overriddenFields`** — what *this instance* changes about the component. A header
  shadow that exists only as an `effects` override on the scrolled instance is invisible in the
  component's own definition.

## The trap, in the form it actually takes

> The export gave `left: 11, top: -9` for a notification badge. Those numbers did not look coherent
> against the parent I had *assumed* the badge hung off, so instead of finding out which node they
> were actually relative to, I looked at a rendered screenshot, judged the badge to be "up and to the
> right", and wrote `top: -8, right: -2`. It shipped clear of the icon it was supposed to overlap.
> The geometry tree had the answer the entire time: the badge was a child of the 16×16 icon frame, so
> those offsets were icon-relative and resolved to an exact overlap.

The geometry tree prints offsets **relative to the parent**. An offset that reads as relative to a
row can be relative to a 16px icon frame inside it. Whose child a node is decides what its numbers
mean.

## Why REST and not the MCP

Quota aside — 200 calls/day on a Pro Dev seat, 6/month on a View seat, keyed off the plan of the team
that *owns* the file — the REST payload states five things the MCP cannot:

| | Dev Mode MCP | REST |
|---|---|---|
| A rotated node | post-transform origin: `x=32 y=32` for a node whose visual top-left is `8,8` | rotation baked in; `rotation` stated |
| Stated vs computed size | `min-h` dropped when a node is read standalone | `minHeight: 112.0` **and** `height: 114.0` |
| A stroked element | geometric `width: 5.245e-7`; painted width unknowable | bounding box **and** `absoluteRenderBounds` (`1.0`) |
| Hidden variants | not exposed | `visible: false` per node |
| Instance overrides | not exposed | `overrides` / `overriddenFields` per node |

The MCP reports a component's **declared** geometry; REST reports the **instance's resolved**
geometry. That is the difference between measuring a hidden variant and measuring what renders.

Style names (`Typography/H4`, `Shadow/lg`) resolve from the payload's own `styles` map — no MCP call.
`get_motion_context` is the one MCP tool with no REST equivalent; if a round needs keyframe data,
say so in the report.
