# Variable names: buy each one once

**If the design binds no variables, none of this applies.** `--vars` reports zero, there is no MCP
call to make, and `--tokens` lists every value under "not bound" — reproduce those exactly. Plenty of
files are built this way.

REST serves every read except variable names. `boundVariables` carries ids
(`VariableID:12:345`); `/variables/local` and `/variables/published` are 403 unless the token has
`file_variables:read`, a scope Figma offers only on Enterprise. The MCP's `get_variable_defs` is
otherwise the only source, and it is metered.

**Names are worth having.** Value alone is lossy: `#0a0a0a` can be *both* `color/text/primary` and
`color/primary`; `#d4d4d4` both `color/border/hover` and `color/text/disabled`. Which semantic slot a
value came from is what tells you whether the design system should expose a semantic token or whether
you are looking at a palette entry used directly.

## The protocol

1. The variable status at the top of `--read` (or `--vars <node>` on its own) reports which of the
   frame's variable ids are still unnamed. **If it reports none, make no MCP call at all.**
2. If there are gaps, spend **one** `get_variable_defs` on the frame.
3. Pipe the payload straight into the merge — it folds into
   `~/.claude/figma/<fileKey>/variables.json`, and nothing is written to disk first:

   ```bash
   python3 $FIGMA_FETCH --vars-merge <node> - <<'JSON'
   { ...payload, verbatim... }
   JSON
   ```

   Then re-read the tree if names were resolved — `--read` is free from the cache, and the values
   section now shows the names instead of `?`.

The dictionary is keyed by Figma file and lives in the home directory, so every worktree, clone and
project pointing at that design file shares one copy. It saturates fast — a design system is finite
and frames reuse it heavily. One call against a single modal named 52–77% of the variables in twelve
unrelated frames of the same file.

## How the merge works

`get_variable_defs` returns names and values but no ids; `boundVariables` gives ids and properties but
no names. The merge matches them on **value, constrained by property kind** — `#0a0a0a` on a text
node can only be a `color/text/*`, a stroke prefers `color/border/*`, a padding only `space-*`.

Text styles resolve **exactly** rather than heuristically: a style's value is a composite naming its
own leaves — `Typography/Body2` is `Font(family: "body/body2/font-family", size: body/body2/font-size,
…)` — so any text node carrying that style pins all five of its typography variables outright.

`--vars` distinguishes three groups: already named, **already looked up and unresolvable**, and never
looked up. It asks for an MCP call only for the last. An id that a defs payload has already failed
to pin down is recorded in `unresolved.json` beside the dictionary, so no later round spends a call
that would produce the same ambiguity.

## Ambiguity is reported, never guessed

Where two variables genuinely hold the same value in the same namespace — `color/background/primary/
default` and `color/background/success/default` both `#0f766e` — the merge prints them as ambiguous
and stores nothing. A later frame using only one of them resolves it. Treat an ambiguous id like any
other value the frame will not settle: decide it, and say so in the report.

## Payload quirks the script already handles

- Typography lives under `node.style`, not on the node.
- A uniform corner radius binds as `rectangleCornerRadii` but stores its value in `cornerRadius`.
- A spacing property bound to a zero-valued variable is omitted from the payload entirely.
