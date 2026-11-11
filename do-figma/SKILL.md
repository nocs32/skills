---
name: do-figma
description: Implement or audit a UI component against a Figma design. Use whenever a Figma link, node id, or design frame is given and the task is to build the component, check that existing code matches the design, or fix visual drift — "implement this design", "match the Figma", "does this component match the design", "here's the frame". Reads frames through the Figma REST API rather than burning the metered Dev Mode MCP quota.
license: MIT
---

# Implementing a Figma component

## The loop

One component at a time. Four steps, and **one of them is the user's**:

1. **Component in.** A Figma URL or node id arrives.
2. **Read, decide, build, verify — one unbroken pass.** Read the frame; find out whether the
   component already exists. If it does, audit it against the frame and fix what has drifted. If it
   does not, build it. Either way prove it in the browser. Do not stop to have findings read back —
   they are not a deliverable on their own and the round trip buys nothing.
3. **Report, and stop.** Everything the approval needs, nothing the conversation already holds:
   what the frame specified, what already existed, what was wrong, what changed (files), what
   `--diff` still lists and why each remaining row is not a defect, the decisions taken where the
   frame was ambiguous, what was deliberately left unwired. State deltas and decisions; do not
   retype the tree, the values list or tool output.
4. **The user approves**, and only then: commit and push.

**Never commit or push without that approval.**

## Every turn is paid for in full

A frame round runs to hundreds of turns on a context of several hundred thousand tokens, and
**every turn re-reads all of it**. The cost of a round is turns × context, so the rules in this
file are about turns: one `--read` to read the frame, one `rg` to search the codebase, one
`measure` and one `--diff` to verify, screenshots to confirm rather than to measure, and a report
that states deltas instead of restating the frame. None of this lowers the bar — every value is
still read from the frame and reproduced exactly; it changes how many turns that takes. Between calls, do not narrate, do not restate tool output, and do
not re-run a read whose result is already in the conversation.

**Existing-or-new is a finding, not a question.** Search before assuming either way — **in one
`rg` call**. `--read` ends with that command, built from the strings the frame renders and the
components it instantiates; add the prop names you would expect and run it once. Read the top hits,
not the whole result. A near-miss component needing a new variant is the common case; quietly
building a second one beside it is the failure. Say which it was.

**Decide, don't ask.** An ambiguous or internally inconsistent frame is still your call: pick the
coherent reading, implement it, and say in the report which way you went and why. A question is only
for something you cannot settle from the frame, the code, or a defensible default — and it goes *in
the report*, never blocking the round.

## Pixel perfect. Not close, not approximately.

**Every value in the frame is a number to be read out of the design and reproduced exactly.** Not
estimated from a screenshot, not inferred from what looks about right, not rounded to whatever is
already in the file. If the design says 4px, it is 4px.

- **A number that does not make sense means you are reading it against the wrong parent** — or the
  wrong node, or the wrong variant. Go find what it is relative to. It does not mean the design is
  vague and you should estimate.
- **Never derive geometry from a screenshot.** Screenshots confirm a result; they never supply one.
- **Measure every value in one sweep.** A string of "one more thing is off" follow-ups means the
  audit was skipped.
- **If the frame genuinely does not give a number**, decide it and record the decision in the report
  and the commit. Never a guess quietly written into the code.

## Reading the frame

`scripts/figma_fetch.py` takes a full Figma URL, or a bare node id once a URL has been used in this
project. **Run `--doctor` first** — it reports the token, the remembered file key and the token
scale, and setup below covers anything it flags.

**The script lives beside this SKILL.md, and the working directory is the user's project, not the
skill.** Set `FIGMA_FETCH` once per session to the path this file was loaded from — the installed
default is below; adjust it if the skill lives in a project's `.claude/skills/` instead.

```bash
FIGMA_FETCH=~/.claude/skills/do-figma/scripts/figma_fetch.py

python3 $FIGMA_FETCH --doctor                    # token, project record, token scale
python3 $FIGMA_FETCH --read   "<figma-url>"      # THE read: variable status + tree + every value
python3 $FIGMA_FETCH --image  "<figma-url>"      # 2x PNG, once, visual sanity check only
```

`--image` is cached per node; a second call returns the same path and the file must not be read
again — an image stays in the conversation for the rest of the session. Read it once, after
`--read`. **Do not crop, zoom or upscale it** with PIL, sips or anything else: every crop is another
image in the conversation, and the render supplies no numbers anyway. It confirms; the tree and the
diff are the numbers.

**`--read` is one call, and it is the whole read.** It prints three sections: the variable status
(whether an MCP call is needed — see below), the geometry tree, and every concrete value in the
frame with its local token. Do not follow it with `--vars`, `--tokens` or the bare tree — those are
the same output in pieces. Do not follow it with grep, jq or python against the cache: **every line
of the tree already carries that node's layout direction, justify/align, fill/hug sizing, padding,
gap, radius, fill, stroke (weight, side, alignment), shadows, blur, opacity, constraints, font
(size/weight/line-height/letter-spacing), text alignment, truncation, text, and instance variant.**
The number you want is on the line of the node that has it. The one legend worth knowing:
`shadow=x,y,blur,spread,#rrggbbaa`; `stroke=#hex/weight[/outside]`; `w=fill h=hug`; `pin=right,bottom`.

**The tree is cut to arrive whole.** `--read` is sized to land inline (~24 KB): past that the
harness parks output in a file and shows 2 KB of it. So on a large frame the tree stops at a depth,
each collapsed subtree ends in `(+N nodes)`, and the header says so. To see inside one, `--read
<that node id>` — and since the work is one component at a time, that inner node is usually the one
to have been reading anyway.

**Never pipe `--read` through `head`, `sed` or `grep`, and never add `--full` or `--depth` in a
session.** They produce output that does not arrive, and then a turn per page to fetch it back.
If what you need is not in the output, it is inside a `(+N nodes)` line: `--read` that id.

**A collapsed subtree is not optional.** Before building anything inside one, `--read` it. The cut
saves the round from a dump that never arrives; it does not license building from the parent's line
alone. **Hidden subtrees collapse too, and those are usually states** — hover, open, error, empty,
selected. A component that has them needs them: `--read` the hidden node to see inside it, and
implement the state.

Run it from inside the project — it locates the project root, its cache and its recorded token
scale from the working directory. Frames cache to `<project>/.figma-cache/`, so re-reads are free.

The raw JSON is only for what the tree does not carry — instance `overrides`, `interactions`, the
per-character `styleOverrideTable` behind a `mixed-styles` text. Reach for it for one named field
on one named node, with one `python3 -c`, and no more often than that. Never write a probe script.

The **values** section splits the frame's values in two, and **both halves have to be reproduced**:

- **Bound to a Figma variable** — these must be written as tokens, never literals. That is what the
  binding means.
- **Not bound** — raw px and hex in the design. Reproduce them exactly. Use a local token where the
  value matches one; where it does not, and the rest of the design *is* variable-driven, that is a
  design-system gap worth flagging in the report.

**Not every design uses variables, and not every project has a token scale.** A design of raw values
is normal — the variable status will say so and there is no MCP call to make. A project with no token scale is
normal too — values report `(no local token scale)` and you reproduce the numbers directly. Neither
is a defect, and neither reduces the pixel-perfect bar.

`** NOT ON THE SCALE **` means a token scale exists but lacks this value: add it to the token source
and say so in the report.

Read `references/reading-a-frame.md` before interpreting geometry — it covers which field answers
which question, and the traps that have produced wrong code.

## The MCP budget

REST serves everything except **variable names**. Those come from the Dev Mode MCP, which is metered
at 200 calls/day. So a name is bought once per variable, *ever*, and cached per Figma file in
`~/.claude/figma/<fileKey>/variables.json` — shared across every worktree, clone and project using
that design file.

**The rule: read the variable status at the top of `--read`, and spend a call only on the ids it
lists as *never looked up*.** It separates those from ids already looked up and found unresolvable —
two variables holding the same value in the same namespace stay ambiguous no matter how often you
fetch, so a second call is waste. When it says "make NO MCP call for this frame", make none.
Otherwise spend exactly one `get_variable_defs` and merge it straight from a heredoc — no file to
write first:

```bash
python3 $FIGMA_FETCH --vars-merge "<node>" - <<'JSON'
{ ...the get_variable_defs payload, verbatim... }
JSON
```

Never more than one call without saying why in the report.

Read `references/variable-names.md` for the merge protocol and how to handle ambiguity.

If the Figma MCP is not connected, carry on — names show as `?`, values still resolve to tokens.
Note it in the report rather than blocking. If the design binds no variables at all, the status says
so and there is nothing to buy.

## Before editing

1. **Read the tree before trusting any generated code.** Whose child a node is decides what its
   numbers mean. When an offset looks odd, check the parent — and check `HIDDEN` — first.
2. **Establish whether the defect is global before editing the component.** If a colour, font,
   radius or variant looks wrong, check whether it is wrong *everywhere* — count the call sites.
   Repair it within this component's scope either way, and put the wider sweep in the report as a
   follow-up. A one-line cause in a theme repaints far more than the screen in front of you, so it
   does not get folded silently into a component round.
3. **State what matches, what is wrong, what is missing, and what is hand-rolled that the design
   system already ships.** The `--diff` output *is* the side-by-side, with node ids — do not retype
   it. The report carries the deltas and the decisions, not the tree.

## Implementing

Follow the project's own conventions — component anatomy, state management, styling, file layout.
Match the surrounding code; read `CLAUDE.md`/`AGENTS.md` and the project's rules if present.

- **Check the design system before adding to a page.** Something generic the kit lacks is a kit
  change plus a call site, not a page-local component. If the kit has a playground or stories, a kit
  change needs its entry in the same commit.
- **A value not on the token scale goes into the token source** — never inline a raw number to hit a
  pixel, and never round to a neighbouring token without saying so. Where the project has no token
  scale, write the raw value and match how the surrounding code expresses it.
- **Stay on the frontend.** Do not add a query, field or endpoint because the frame shows data the
  app lacks. Render from what exists (constant, fixture, labelled mock), shape the component so the
  value arrives as a prop, and say in the report that it is unwired.

## Verifying

Discover the project's own commands — `package.json` scripts, `CLAUDE.md`, the Makefile — rather
than assuming. Typecheck and lint always; most frontend suites cover pure functions only, so
**anything visual needs the browser**.

**Dev servers belong to whoever owns the checkout.** Ask rather than starting one.

**Verification is two calls, not one per node.** Paste `scripts/measure.js` into the browser's JS
tool followed by a single `measure(rootSelector, { '<node id>': '<selector>', … })` naming every
node that matters; hand the JSON it returns to `--diff` in a heredoc. If you do not know the
selectors yet, one `inspect(rootSelector, 4)` first prints the DOM under the root as an outline
with boxes — pick every selector from that one output, not from an `outerHTML` slice per turn.

```bash
python3 $FIGMA_FETCH --diff "<root node>" - <<'JSON'
{ ...measure() output, verbatim... }
JSON
```

It prints only what differs — the frame's number and the DOM's, side by side — and annotates the
Figma-vs-CSS differences that are not defects. Fix, re-measure, re-diff. **Never measure one node
per turn with `getBoundingClientRect`, and never inspect one element per turn with `outerHTML`**:
every turn re-reads the whole conversation, and this is the phase where it is largest. After the
first `measure`, a follow-up question about one element is answered by another `measure` with that
element added to the map, or an `inspect` narrowed to it — one call either way.

**Screenshots confirm; the diff proves.** Two per component is the norm — before and after. More
only for what `measure` cannot reach: a hover or open state, an overlay, something under a transform
(`references/verification.md` covers those).

Read `references/verification.md` for the traps in measuring, and for the Figma-vs-CSS differences
that look like defects and are not.

## First run in a project

Do this yourself, before reading the frame. It costs the user one question, once per project.

1. **`python3 $FIGMA_FETCH --doctor`.**
2. **`token MISSING`** → stop and ask the user to create a Figma personal access token (figma.com →
   Settings → Security → Personal access tokens) and export it as `FIGMA_ALL_ACCESS`. You cannot
   create it for them and nothing works without it. **This is the only step that needs a human.**
3. **`token scale NOT CHECKED`** → find the project's design-token source: a directory or single
   file of TS/JS object literals, CSS custom properties, SCSS/Less variables, or JSON (including
   the DTCG `$value` format). Check `CLAUDE.md` and the design-system package first. **Confirm your
   candidate with the user before recording it** — a wrong guess maps values onto the wrong scale —
   then record the answer, including when the answer is "there isn't one":

   ```bash
   python3 $FIGMA_FETCH --set-tokens src/theme/tokens --prefix theme
   python3 $FIGMA_FETCH --set-tokens none     # plenty of projects write px and hex directly
   ```

   It prints what it found by kind and names the categories that are not tokenised, so a wrong
   directory is obvious immediately. Recording `none` stops later sessions hunting for a theme file
   that does not exist.
4. **Add `.figma-cache/` to the project's `.gitignore`** — or to `.git/info/exclude` if the user
   would rather not commit the rule.

Everything after that is remembered: settings live in `~/.claude/figma/projects/<project>.json`,
keyed by git remote, so worktrees and clones of a repo share one record. The file key comes from the
first Figma URL you are given, after which bare node ids work. **Nothing is written into the project
except the frame cache.**

The values section of `--read` states which case every value is in:

| Output | Meaning |
|---|---|
| `theme.spacing.s16` | use this token |
| `** NOT ON THE SCALE **` | the scale covers this category but lacks this value — a real gap; add it |
| `(no radius scale — write the raw value)` | this category isn't tokenised here; raw is correct |
| `(raw value — this project has no token scale)` | recorded as having none; write the number |

A recorded token path that **stops resolving** is fatal, by design: silently dropping the scale is
how literals end up in code that should carry tokens.
