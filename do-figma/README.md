# do-figma

A Claude Code skill for implementing and auditing UI components against Figma designs.

It reads frames through the **Figma REST API** instead of the Dev Mode MCP, which is metered at
200 calls/day. Variable *names* are the one thing REST cannot serve, so they are bought once each
from the MCP and cached per Figma file in `~/.claude/figma/<fileKey>/variables.json` — shared across
every worktree, clone and project using that design file.

## Install

Copy it from this repository into your personal skills folder:

```bash
git clone https://github.com/nocs32/skills.git
rm -rf ~/.claude/skills/do-figma && cp -R skills/do-figma ~/.claude/skills/do-figma
```

The `rm -rf` matters on an update: `cp -R` into a directory that already exists copies *inside*
it, leaving the old files in place and the new ones in a nested `do-figma/do-figma/` that is never
loaded. Re-run the line after a `git pull`. The skill is loaded at the start of a session, so
restart open sessions to pick up a new `SKILL.md`; the scripts are read from disk on every run.
It is then available as `/do-figma` — or simply by pasting a Figma link and asking.

Dropping it into a single project's `.claude/skills/` works too, if you want it scoped to one repo.

## Set up

One step, because it is the only one you can't delegate:

```bash
export FIGMA_ALL_ACCESS="figd_..."
```

Create the token at figma.com → Settings → Security → Personal access tokens, and put that line in
your shell profile.

That's it. The first time you use the skill in a project it checks its own setup, works out where
the project keeps its design tokens (asking you to confirm before it records the answer), remembers
the Figma file key from the link you paste, and gitignores its cache. Nothing to configure by hand.

## Use

Paste a Figma link and say what you want:

> Implement this design: https://figma.com/design/abc123/App?node-id=1-23

> Does our Card component match this frame? https://figma.com/design/abc123/App?node-id=1-2

## The tool on its own

The skill drives this for you; run it directly only if you want to look at a frame yourself.

```bash
FIGMA_FETCH=~/.claude/skills/do-figma/scripts/figma_fetch.py

python3 $FIGMA_FETCH --doctor       # token, project record, token scale
python3 $FIGMA_FETCH --read   URL   # one call: variable status + tree + every value with its token
python3 $FIGMA_FETCH --image  URL   # 2x PNG render, cached per node
python3 $FIGMA_FETCH --diff   URL measured.json   # compare a measure.js reading with the frame
```

`--read` is sized to land inside the harness's inline output limit (~24 KB), because past that a
tool result is parked in a file and only a 2 KB preview reaches the agent. The values section is
grouped by property to stay small; the tree takes the rest, cut by depth on large frames, each
collapsed subtree ending in `(+N nodes)` for `--read <that id>` to expand. `--depth N` and `--full`
exist for a human at a terminal. `--vars`, `--tokens` and the bare tree remain as the pieces.

`scripts/measure.js` is the other half of verification: pasted into a browser console,
`inspect(root, 4)` prints the DOM under a root as an outline with boxes, one
`measure(root, { nodeId: selector, … })` call reports every target's box and computed styles, and
`--diff` prints what differs from the frame.

Requires Python 3.9+ and no third-party packages. A full Figma URL works anywhere a node id does.

## Licence

MIT
