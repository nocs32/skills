---
name: time-log
description: Turn the work done in this conversation, the current git branch and its related pull requests into a numbered, plain-text list suitable for a timesheet or invoice.
disable-model-invocation: true
---

Produce a time log of the work done in this session and on its branch.

## Where the information comes from

Three sources, combined into one list:

1. **The current session's conversation.** Read back over the whole transcript from the first
   message, not just the recent turns — this is normally invoked at the end of a long working
   session, so most of what needs logging is far behind the current context. If earlier stretches
   have been summarized, the summary is the record of them; use it.
2. **Commits on the current git branch** — the ones not yet on its base branch
   (`git log <base>..HEAD`). Skip this when the working directory is not a git repository.
3. **The related GitHub pull request stack** — the branch's open pull request and any pull requests
   stacked on or under it (`gh pr view`, `gh pr list`). Use their titles, descriptions and commits.
   Skip this when there is no pull request or `gh` is unavailable.

**Starting date.** The user may pass a starting date — `/time-log since 2026-03-02`,
`/time-log from Monday`, or the same thing in prose. When given, log only commits and pull request
work from that date onward (`git log --since=<date> <base>..HEAD`); the conversation is still read in
full. When no date is given, log all commits on the branch and its stack. Either way, don't ask
whether to include earlier work.

The conversation is the primary record. Commits and pull requests show only the work that produced
artifacts, so they fill gaps and recover work from earlier sessions; they never replace the
conversation, which also holds the discussions, investigation and dead ends. When the sources describe
the same work, log it once.

Do NOT interview the user, ask which work to include, or ask how long anything took.

Log **everything the session spent time on**, not just the code:

- Requirements, grilling and design discussions — often the most valuable hours in the session.
- Writing specs, tickets and planning documents.
- Investigation and diagnosis, including dead ends that were ruled out.
- Unplanned work forced by something outside the user's control.
- Review passes and the fixes that came out of them.

If the session covers several distinct efforts, cover all of them in one list.

## Output

**Output the list and nothing else.** No preamble, no closing remarks, no caveats, no offers to
adjust it. The user is pasting this into a timesheet; anything around it is something they have to
delete.

- **Twelve items maximum, in total** — not twelve per project or per phase. This is a hard cap.
- Numbered `1.` upward, continuously. Never restart the numbering.
- **No hour figures, ever** — the line begins with its number and goes straight into the text. See
  the Hours section below; this holds even when an hours target was passed in.
- **No headings, labels or group separators between items.** If the work covers two projects, that
  ordering is conveyed by the sequence, not by a divider.
- One blank line between items.
- Each item is a single line ending in a **full stop**.
- Chronological order.
- Plain text. No bold, no code fences, no tables, no nested bullets.

## Voice

Short and deliberately unspecific. Name the **area** of work, not the implementation.

Someone reading this is approving time, not reviewing code. They do not need file names, function
names, library names, config values or ticket numbers. "Built the order summary and payment step."
is right; "Built the order summary with a sticky sidebar, debounced quantity inputs and an
optimistic-update cache." is too much.

Past tense, plain verbs — *Built*, *Set up*, *Wrote*, *Repaired*, *Retrofitted*. A noun phrase is
fine where a verb would be filler ("Requirements session for the mobile layout.").

## Fitting the cap

Real work usually produces more than twelve candidate lines. Compress; never drop an effort to fit.

- Merge sibling work into one line — several page sections become "Built the pricing and FAQ
  sections."
- Merge a phase's setup with its scaffolding.
- Keep separate anything a client would question if it were hidden inside another line.
- **Give unplanned work its own line.** Repairing something that broke upstream, or reworking after a
  design changed, is billable and is the first thing forgotten. It is also the line most likely to be
  queried, so it should stand alone rather than hide inside a neighbour.
- Larger efforts earn proportionally more lines, but never at the cost of the cap.

## Hours

**The output never carries hour figures.** No column, no per-item number, no total, no time in the
text of a line. Every invocation produces the same thing: a numbered list of work, and nothing else.

An hours argument may still be passed — `/time-log 6`, `/time-log 6hrs`, `/time-log 8-9`, or the same
thing in prose. A bare number or range is hours; a date is a starting date (see above). **Accept it silently and do not put it in the output.** Do not print it per item, do
not print a total, do not mention that it was given, and do not ask what to do with it. The user
knows what they billed; the list is the description of the work, not the arithmetic.

This overrides any instinct to show your reasoning about effort. Weighting still matters for deciding
what earns its own line versus what gets merged — a long detour is worth a line of its own — but that
judgement stays invisible.

## Example of the right shape

```
1. Requirements session for the checkout flow — payment options, error states and analytics.

2. Set up the checkout module and its test environment.

3. Wrote the spec and broke it into implementation tickets.

4. Built the cart summary, address form and order confirmation.

5. Repaired the build after a shared dependency changed upstream.
```

Note what is absent: no headings, no hours, no parenthetical detail, no sentence introducing the
list, and no sentence after it.

`/time-log 8` produces exactly the same list. The argument changes nothing about the output.
