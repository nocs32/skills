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
