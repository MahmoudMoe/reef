# Constitution — {{name}}

Non-negotiable principles. Every task, plan and PR is checked against these. Amending this file is itself a queue item and requires an ADR; the version below moves with it.

Ratified: {{date}} · Version: 1.0.0

Each article says what it prevents. Keep 8–15; a rule nobody can name the cost of is decoration.

## Article I — Spec before code, not approval before code
No implementation starts without a task file (`tasks/NNN-slug.md`) stating the problem, the acceptance criteria (each naming its test) and what is out of scope, pushed first. The loop then proceeds on its own; it stops only for a decision that is the owner's, a missing credential or quota, a spec found wrong mid-build, or the round cap. *Prevents:* building the wrong thing with nothing to check it against, and a loop that halts at every phase and becomes a queue.

## Article II — One item, one branch, one PR
Each queue row is independently shippable: its own branch, its own PR into the integration branch, the app still working after it. No PR bundles two rows; no row spans two PRs without being split in the queue first. *Prevents:* a review that cannot say what it is reviewing.

## Article III — The round cap
Each item gets at most the number of fix rounds in `.reef/config.json` `caps.attempts`, across review, verification and CI together. Not green after the last one: the loop halts on that item, writes the blocker into `docs/journal.md`, escalates. No "just one more fix". *Prevents:* the fourth round that fixes the third round's fix.

## Article IV — Decisions are recorded
Any choice that forecloses an alternative — a model, a protocol, a data shape, a vendor, a process rule — becomes an ADR in `docs/adr/` before the PR that depends on it merges (drafts unnumbered; numbered at merge). "We discussed it" is not a record. *Prevents:* the same decision re-argued in every review.

## Article V — Claims are verified, not assumed
"It builds" is not "it works". Anything measurable is measured and the evidence committed; what could not be verified is said so plainly, with the probe that was run. A sentence about the code that the code does not keep is a defect of the same class as a wrong line. *Prevents:* the review round spent on a false sentence.

## Article VI — Simplicity gate
Prefer the framework's own feature over a wrapper, one model of a thing over a mapped pair, deleting over adding. A guard refuses by shape with a small closed exception list; it is never narrowed into "pass unless listed". *Prevents:* complexity that hides the next defect.

## Article VII — The batch boundary is fixed
When a batch starts, its contents freeze. Anything discovered while it runs is queued to the next batch, unless it loses a person's data, exposes a secret or personal data in merged code, or leaves the product visibly broken for the owner — and using the exception is journaled with its ground. *Prevents:* a roadmap that never advances while every single decision looks right.

## Article VIII — Secrets and personal data have a boundary
No secret in the repository, in a log or in a stack trace; personal data has a retention period, a defined audience and a deletion path, and is enforced at the data-access boundary, not by remembering. Cost caps are enforced server-side before the spend. *Prevents:* the leak that is found by a reviewer instead of a test.
