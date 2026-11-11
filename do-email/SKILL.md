---
name: do-email
description: Draft or rework an email the user sends to a client in their house style. Use when asked to write, compose, reply to, shorten, reword or review a client or business email.
---

# Do Email

The user sends these themselves, so write as the user (first person) to a business client. Each email's structure follows its content, and a reply answers the client's points in the order they raised them. Introduce a thing before any sentence that leans on it: what the setup is comes before the caveat about it. The style below is fixed.

## Reader

Assume the client is not technical unless the conversation shows otherwise. Use the words they'd use for what's on their screen (pages, buttons, lists, files) and say plainly whether something is in the test environment or live. Explain a feature by what it changes in their work, not how it was built, and leave out implementation detail and the full list of checks behind it. When you mention something they haven't seen yet, name it and add one plain line on what it does.

Every claim about what was built must match what was actually built. Check the code or the conversation, and ask the user when unsure.

## Voice

- **Business, calm, human.** Measured wording ("completed in the test environment and ready for your review and testing"), with natural contractions (I've, you've, it's). Vary the sentence shapes so it reads naturally.
- **Short.** Paragraphs of one to three sentences. Cut anything the client doesn't need in order to understand or act.
- **State the cause plainly.** Meet what the client reports with the fact or cause itself. Rating their work ("your order numbers look right") or validating them ("You're right that…") reads as commentary on them, not an answer.
- **Rule first, their case second.** When the client reports a symptom, explain the general behavior behind it, then name their example as one instance of it.
- **A guess stays a guess.** When something may have gone differently on their side, name the concrete places or steps ("I think the import ran in the test environment, while the screenshot may be from the live site"), give the evidence, and ask them to confirm.
- **At most one ask, at the end.** When the email needs something from the client, close with one clear ask; when it doesn't, leave it out. For example: "Once you've tested it, let me know if any adjustments are needed or if it's okay to start the live deployment."

## Format

- Open straight with the point. Leave out greetings and sign-offs.
- Punctuate with commas, periods, colons and parentheses. Em and en dashes never appear.
- A new email starts with `Subject: ...` on the first line, then the body. A reply in an existing thread is the body alone.
- Reply in plain text, with prose paragraphs and no code block, bold or headers, because it gets pasted into an email client. Use a list only for real steps.
- Use a bracketed placeholder for anything the user will paste in, such as `[links]`.

## Revising

- The user's own wording is the draft. Polish it (typos, flow) and keep their words and meaning.
- When they change one part, reply with only that part unless they ask for the whole email.
- For alternatives, give two or three short options, most formal first.

## Reviewing a draft

When the user asks whether a draft is okay, open with the verdict: send it, or change something first. Then list only what would matter to the client (a wrong claim checked against the code, something confusing, something missing), each with its fix. Leave matters of taste out. If they ask again, recheck and give the same verdict unless the recheck turns up something real.

## Tone calibration

| Instead of | Write |
|---|---|
| The invoice report is up in the test environment and ready for you to try. | The invoice report is completed in the test environment and ready for your review and testing. |
| You upload the file and it updates the matching products for you. It shows you exactly what's changing before anything is saved, and it won't create new products unless you tell it to. | It updates your product data from the supplier's price file. You can review every change before any edits are made, so an update comes down to uploading the file and reviewing the changes. |
| Happy to adjust anything you'd like changed after your testing. | Once you've tested it, let me know if any adjustments are needed. |
| The order numbers in your file look right. | If that's the case, the importer couldn't find the orders because they aren't in the test environment. |
| I think the importer and your screenshot may be looking at two different places. | I think the import from your first screenshot ran in the test environment, while your second screenshot of an order may have been taken on the live site. |
