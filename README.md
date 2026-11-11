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

### [do-email](do-email/SKILL.md)

Drafts, rewrites and reviews the emails you send to clients, in one fixed house style: written as you, calm and businesslike, short paragraphs, plain words a non-technical client understands, and a single clear ask at the end when one is needed. Output is plain text with no greeting, sign-off or dashes, ready to paste into your email client. It answers the client's points in order, states causes plainly instead of judging their work, treats your own wording as the draft, and checks every claim about what was built against the code or the conversation. A tone table shows typical rewrites.

Example:

> write the client an email that the supplier price import is ready to test

> Subject: Supplier price import ready for testing
>
> The supplier price import is completed in the test environment and ready for your review and testing.
>
> It updates your product prices from the supplier's file. You can review every change before anything is saved, so an update comes down to uploading the file and checking the list.
>
> Once you've tested it, let me know if any adjustments are needed or if it's okay to start the live deployment.

Possible applications:

- Status updates when a feature is ready for the client to review
- Replies to bug reports and "this doesn't look right" questions
- Polishing a rough draft you wrote yourself without changing what it says
- A quick send-or-fix verdict on a draft before it goes out
- Keeping one consistent voice across every client email

### [do-figma](do-figma/SKILL.md)

Builds a UI component from a Figma frame, or audits an existing one against it, to the exact pixel. It reads frames through the Figma REST API with the bundled `scripts/figma_fetch.py`, so it doesn't use up the metered Dev Mode MCP quota. It only calls the MCP for variable names it has never seen, and caches them per design file. One read returns the layout tree, every value with its matching local design token, and a search that shows whether the component already exists. After building, `scripts/measure.js` measures the result in the browser and `--diff` lists only the values that still differ from the frame. It stops for your approval before committing. Needs Python 3.9+ and a Figma personal access token in `FIGMA_ALL_ACCESS`; see [do-figma/README.md](do-figma/README.md) for setup.

Example:

> Does our Card component match this frame? https://figma.com/design/abc123/App?node-id=1-2

> The frame specifies 16px padding, a 12px gap and an 8px radius; the existing Card had 12px padding and a 6px radius. Fixed both in `Card.tsx` and added `radius.r8` to the token scale. `--diff` now lists only the title's height, +5px, which is Figma trimming text boxes, not a defect.

Possible applications:

- Implementing a new component from a design handoff
- Checking that an existing component still matches the design after a redesign
- Finding values that were eyeballed or rounded instead of read from the design
- Spotting gaps between the design's variables and the code's token scale
- Saving Dev Mode MCP quota on teams that read a lot of frames

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

## License

[MIT](LICENSE)
