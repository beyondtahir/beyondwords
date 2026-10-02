# Story Bible Pattern — Long-Form Fiction Continuity

Use for novels and any multi-chapter fiction. The goal: continuity stays deterministic without stuffing the whole manuscript into context.

## Contents
1. The story bible
2. Accept-before-canon
3. Last-3-chapters summary memory
4. Chapter contracts for fiction
5. Final lint

## 1. The story bible

Maintain `story-bible.md` (see `assets/story-bible-template.md`) as the single source of truth:

- **World/setting** — places, rules, timeline.
- **Characters** — one card each: name, age, appearance, want, wound, voice quirks, relationships.
- **Facts ledger** — every established fact with the chapter it came from ("Chapter 4: Mara has never flown").
- **Chapter log** — one-paragraph summary per accepted chapter.

Update the bible only when a chapter is accepted. Facts cite their source chapter so contradictions can be traced.

## 2. Accept-before-canon

- Generate → user reviews/edits → **accept**. Only accepted chapters enter canon and the chapter log.
- Revision can be paragraph-scoped; never silently regenerate an accepted chapter.
- This gate is what keeps drift out of long projects.

## 3. Last-3-chapters summary memory

When drafting chapter N, supply the model with:

1. The chapter contract (below).
2. Summaries of the last 3 accepted chapters (from the chapter log, tail-capped).
3. Only the bible facts relevant to this chapter's characters/location — not the whole bible.

This bounded context beats dumping the entire manuscript: cheaper, and it prevents the model from re-writing old plot.

## 4. Chapter contracts for fiction

Each chapter gets an immutable contract before drafting (see `assets/chapter-contract-template.md`): chapter number, title, role (regular/bridge/climax), purpose, characters present, location, foreshadowing planted/paid off, summary of the planned beats. Drafts are checked against the contract; if the draft breaks the contract, fix the draft — or explicitly amend the contract with the user's approval. Never drift silently.

## 5. Final lint

After the last chapter is accepted: run `scripts/bw_lint.py` on the assembled manuscript, then assemble the export with `scripts/bw_build.py`. Fix flags by hand-editing the specific chapter and re-accepting it — do not regenerate wholesale.
