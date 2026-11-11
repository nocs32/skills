---
name: do-stacks
description: Re-cut a long-lived branch into a stack of per-layer PRs on GitHub (docs first, backend on them, frontend on top), tree-checked and verified at every tip, linked with gh stack.
disable-model-invocation: true
---

# Re-cutting a branch into a stack

A branch that grew backend and frontend work together lands as **one PR per layer**, stacked so
each review sees only its own diff and the trunk gets one commit per PR. The source branch is never
touched; the stack is rebuilt beside it from its commits.

## Inputs

- **Source** — the branch to re-cut. **Trunk** — what it will land on (the repo's default branch
  unless told).
- **Layers**, bottom to top: the bottom is the first in the stack, built on the trunk, and each
  layer after it is built on the one before. One line per layer, `<branch>|<scope>|<path-regex>`.
  Build the spec from the repo's real layout; for a repo with docs, an API and a web app it looks
  like:

  ```
  feature/<thing>-docs|docs|^(docs/|\.claude/|CONTEXT\.md$|[^/]+/docs/)
  feature/<thing>-api|api|^(schema/|api/)
  feature/<thing>-web|web|^web/
  ```

  The docs layer is the first in the stack: decision records, rules and glossary terms are the
  starting point the code follows, so they land alone and before it. A module's own `docs/` rides
  in it too — the first layer whose regex matches a file claims it. A shared contract (an API
  schema, generated types' source) rides with the layer that produces it, below the layers that
  consume it: their codegen reads it, so it has to land first. A branch that also touches another
  module gets a layer of its own on top, e.g. `feature/<thing>-admin|admin|^admin/`. Leave out a
  layer the branch does not touch — the script would still build its branch, and the stack would
  carry an empty PR.

  A file no layer claims (the lockfile, CI config, root tooling) follows the commit it arrives in —
  the lockfile rides with the dependency commit that changed a manifest, so a layer's tip never
  carries a lockfile its manifests don't explain. That holds only while the commit's claimed files
  sit in one layer. When they span layers, or the commit claims none, the script sends its
  unclaimed files to the first code layer — the first whose scope is not `docs`, since the docs PR
  carries documents only. A dependency commit whose manifests span layers (`web/package.json` with
  `api/package.json`) then has its lockfile away from one of them, and `--plan` marks it `WARN`.
  Split it by hand on the source before building: one dependency commit per layer, each with only
  its own manifests and the lockfile change they produce.

  The script recognises the common JavaScript lockfiles and `package.json` manifests. For another
  ecosystem, set `LOCKFILE_RE` and `MANIFEST_RE` (extended regexes) before running it.

Ask only for `<thing>` when the user gave no branch names. Write the spec to the scratchpad.

## Steps

1. **Plan.** `scripts/split-stack.sh <source> <trunk> <spec> --plan` prints, per layer, which
   commits are picked whole and which are split. Read it for the one thing the script cannot judge:
   a commit split across layers whose halves cannot stand alone (a frontend change that only
   compiles against a schema change in the same commit is fine — the frontend layer sits on the
   backend layer; the reverse is not).
2. **Build.** Run the script without `--plan`. It checks the layer branches out in turn; a conflict
   stops it with the branch at the last good commit and the failing commit named. Resolve by hand
   (apply the path-restricted patch, commit `--no-verify` with the layer's scope) and rerun with
   `--from <next-commit> --layer <branch>`. A `does not match index` failure is a file watcher
   having touched a file mid-run: rerun from the same commit.
3. **Tree-check** before anything else. For **every layer** `L`, with `<below>` the layer under it
   (the trunk for the bottom) and `<above>` the paths of every layer over it, two diffs, both
   **empty**:

   ```bash
   git diff --stat <below> <L> -- <above>             # L carries nothing of the layers above it
   git diff --stat <source> <L> -- . ':!<above>'       # L carries all of its own layer and those below
   ```

   The top layer has nothing above it, so it skips the first diff and runs only the second, as
   `git diff --stat <source> <top>`: the top tip is the source, exactly. The docs layer runs its
   second diff over its own paths only, `git diff --stat <source> <docs> -- <docs paths>`, since
   the unclaimed files of code commits sit in the layers above it. A non-empty diff is a
   classification bug in the spec, not something to patch on the branch.
4. **Verify every tip**, bottom to top, with the repo's own commands — take them from its
   `CLAUDE.md`, `AGENTS.md` or package scripts, each run from its module's folder. At each tip: the
   layer's own module's codegen, typecheck, lint and test suite, **and** codegen + typecheck of
   every module in the layers above — those sit at the state of the tip below them, which is
   exactly what the trunk looks like once the stack has landed up to this layer.

   Write the commands down per module before starting, for example:

   | Module | Codegen | Typecheck | Lint | Tests |
   |---|---|---|---|---|
   | `api` | `npm run codegen` | `npm run typecheck` | `npx eslint <changed files>` | `npm test` |
   | `web` | `npm run codegen` | `npm run typecheck` | `npx eslint <changed files>` | `npm test` |

   The docs layer has no module and changes no code, so its tip is checked by the tree-check
   alone. Revert regenerated files afterwards. A failure at a tip is a commit in the wrong layer —
   fix the spec or the split, rebuild; never a fix-up commit.
5. **Publish.** Push every layer branch; open one PR per layer, each based on the branch below (the
   bottom on the trunk), body written from the commits — what the layer changes and why — with a
   **Stack** line naming the PRs below and above. When the repo has a PR template in `.github/`,
   the body follows its shape and length. When the repo labels PRs, add a `--label` for each module
   the layer touches. Then link them, every layer bottom to top:

   ```bash
   gh extension list | grep -q gh-stack || gh extension install github/gh-stack
   gh stack init --base <trunk> <layer-1> <layer-2> [<layer-3> …]
   gh stack link <pr-1> <pr-2> [<pr-3> …]
   ```

   `gh stack view` must show the chain ending in the trunk.
6. **Report and stop.** Table of PR → branch → base → commit count; which commits were split and
   what their new scopes are; what ran at each tip; what is left to the user: land the stack
   bottom to top, one PR at a time (`gh stack merge`, squash) — each merge retargets the PR above
   it to the trunk — then close the source PR and delete the source branch. Leave the checkout on
   the top branch.

## Commit messages

If the repo enforces a scoped commit format (commitlint, a `commit-msg` hook), the script still
writes its commits `--no-verify`: it re-lays history from before the hook, and a layer may span
scopes (a schema folder and the API module in the backend layer is normal). A split commit's
subject gets its layer's scope; a whole commit keeps its own, so a `schema` commit stays `schema`.
A whole commit with the catch-all scope `all` takes the layer's scope. Both `type(scope):` and
`type[scope]:` subjects are handled; a subject with no scope is left as is. Nothing new is
authored here, so nothing bypasses the rule that matters.
