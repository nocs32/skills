# Skills

A collection of custom agent skills for Claude Code and other agents that support the skills format.

## What's a skill?

A skill is a folder containing a `SKILL.md` file: a short frontmatter block (`name`, `description`) followed by instructions an agent loads when the task matches. Skills can also bundle supporting files such as scripts, templates and reference docs.

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
