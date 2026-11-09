# Skills

A collection of custom agent skills for Claude Code and other agents that support the skills format.

## What's a skill?

A skill is a folder containing a `SKILL.md` file: a short frontmatter block (`name`, `description`) followed by instructions an agent loads when the task matches. Skills can also bundle supporting files such as scripts, templates and reference docs.

## Skills

### [quick-estimate](quick-estimate/SKILL.md)

Turns a short task description into a conservative hour estimate with a brief breakdown. It splits the work into parts, adds the work that usually gets forgotten (testing, deployment, permissions, review fixes), applies a contingency multiplier and rounds up to a fixed scale. It states its assumptions instead of asking questions, unless the request has almost no context.

Example:

> estimate - add "forgot password" with an emailed reset link to an existing login page

> **Estimate: 6h**
>
> - Reset token and endpoints - 2h
> - Reset form and validation - 1h
> - Email template and sending - 1h
> - Tests and deploy - 2h
>
> Assumes: an email provider is already configured, no rate limiting beyond what exists.

Possible applications:

- Answering "how long will this take?" for a ticket, feature request or bug report
- Pricing small pieces of client or freelance work before sending a quote
- Sanity-checking your own gut estimate during sprint planning or backlog grooming
- Comparing options quickly ("rebuild vs. patch") by estimating each one
- Producing a consistent first number that a team can then discuss and adjust

### [time-log](time-log/SKILL.md)

Turns a working session into a short, numbered list of what was done, ready to paste into a timesheet or invoice. It reads the conversation, the commits on the current branch and the related pull request stack, and logs all of it, including discussions, investigation and unplanned fixes, not just the code. The list is capped at twelve chronological lines, written at the level of "what area was worked on" rather than implementation detail, with no hours and nothing around it. It runs only when invoked (`/time-log`), optionally with a starting date (`/time-log since Monday`) to leave out older commits.

Example:

> /time-log

> 1. Requirements session for the checkout flow — payment options, error states and analytics.
>
> 2. Set up the checkout module and its test environment.
>
> 3. Built the cart summary, address form and order confirmation.
>
> 4. Repaired the build after a shared dependency changed upstream.

Possible applications:

- Filling in a daily or weekly timesheet at the end of a session
- Writing the line items for a client invoice
- Recovering what happened on a long-running branch spread over several sessions
- Producing a status update or standup summary for a manager or client
- Making unplanned work (upstream breakages, design changes) visible so it gets billed

### [do-stacks](do-stacks/SKILL.md)

Re-cuts a long-lived branch that mixes docs, backend and frontend work into a stack of pull requests, one per layer, each based on the one below. You describe the layers as path regexes; the bundled `scripts/split-stack.sh` replays the branch's commits onto each layer branch, splitting commits that span layers and keeping their author, date and message. Every layer is then tree-checked against the source branch and verified with the repo's own codegen, typecheck, lint and tests before the PRs are opened and linked with `gh stack`. The original branch is never touched. It runs only when invoked (`/do-stacks`).

Example spec:

```
feature/search-docs|docs|^docs/
feature/search-api|api|^(schema/|api/)
feature/search-web|web|^web/
```

> /do-stacks feature/search onto main

> | PR | Branch | Base | Commits |
> |---|---|---|---|
> | #41 | feature/search-docs | main | 2 |
> | #42 | feature/search-api | feature/search-docs | 5 |
> | #43 | feature/search-web | feature/search-api | 7 |

Possible applications:

- Turning a branch that got too big into PRs a reviewer can take one at a time
- Landing decision records and docs before the code that follows them
- Making sure each layer builds and passes tests on its own, not only the finished branch
- Keeping trunk history at one clean commit per layer

## Layout

```
<skill-name>/
  SKILL.md        # frontmatter + instructions
  ...             # optional supporting files
```

## Usage

Copy or symlink a skill folder into your agent's skills directory, for example:

```bash
ln -s "$(pwd)/<skill-name>" ~/.claude/skills/<skill-name>
```

The skills here are generic and meant to be adapted to your own projects and conventions.
