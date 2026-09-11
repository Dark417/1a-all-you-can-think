---
name: create-demo
description: Produce or refresh the public-facing presentation of a repo — a high-level README, an architecture SVG, and a demo/ folder written for non-technical readers plus ready-to-paste LinkedIn/Reddit/Discord posts. Use when the user says "create demo", "update the readme", "make it presentable", "write the post", or when a repo reaches a milestone worth showing.
---

# create-demo

Turns finished work into something a **non-engineer can understand in 60 seconds**
and an engineer can verify in five minutes.

Usage: `/create-demo <repo-dir>` (e.g. `1sde-edgar-01-contracts`). Default:
the repo the conversation is about. Never run it across several repos at once —
each repo's story is different and a batch run produces boilerplate.

## The split — this is the whole point

| Artifact | Audience | Rule |
|---|---|---|
| `README.md` | someone who landed here from a link | **High level only.** What it is, the picture, the links. If a sentence contains a threshold, a flag, a test name, or a version pin, it does not belong. |
| `demo/architecture.svg` | everyone | One picture: the flow, left to right. Not a class diagram. |
| `demo/README.md` | clients, recruiters, non-technical readers | The **story**: what problem, why it is hard, what was built, what you can see. Plain language. No jargon without a plain-English gloss in the same sentence. |
| `demo/walkthrough.md` | someone evaluating it | A guided tour: what to click or run, what to look for, what it proves. |
| `demo/posts.md` | you, copy-pasting | Three drafts, three different tones. Ready to send, not templates to fill in. |
| `docs/` | engineers | **Untouched.** Design docs stay design docs. This skill never edits them. |

**`demo/` is not documentation.** It is explanation. If a reader needs to know
what a MERGE is to follow it, rewrite the sentence.

## Procedure

1. **Read before writing.** The repo's `README.md`, `AGENTS.md`, `docs/`, recent
   `git log`, releases, and CI status. Never describe a feature you have not
   confirmed exists — check the code or the release, not the plan.
2. **Establish what is actually true today.** Which features are built, which are
   design-only, what is deployed, what the live link is (if any). Write this down
   before drafting; it is the fact base for everything else.
3. **Find the one interesting idea.** Every repo has exactly one thing worth
   leading with. Not a feature list — the decision that made it non-obvious. If
   you cannot name it in a sentence, keep reading before you start writing.
4. **Draft the SVG** (see below), then `demo/README.md`, then `demo/walkthrough.md`,
   then `demo/posts.md`, then trim the repo `README.md`.
5. **Verify** — run the checks below and fix anything they catch.
6. **Report** what changed and what still needs a human (a screenshot, a live
   link, a number you could not confirm).

## The architecture image

Hand-author an **SVG** at `demo/architecture.svg`. No build step, no dependency,
renders on GitHub, opens in any browser, and exports cleanly to PNG (below) for
platforms that will not render SVG.

Rules that make the picture actually readable:
- **Left to right, one flow.** Data moves one way; put it on one axis.
- **Six boxes maximum** at the top level. If you need more, you are drawing a
  design doc, not an explanation.
- **Label the arrows, not just the boxes.** "gzip NDJSON" on an arrow teaches
  more than a box labelled "Ingest".
- **Highlight this repo** in the whole-project picture, so a reader sees where it
  sits before they read a word.
- **Readable at thumbnail size**: ≥14px text, high contrast, no thin grey lines.
- **Works on both light and dark backgrounds** — GitHub renders README images on
  either. Explicit `fill` on every shape and text; never rely on a default.
- No gradients, no shadows, no clip art, no logos you do not own.

**Also export a PNG.** GitHub renders SVG, but LinkedIn and Discord do not.
Render at 2x so it stays sharp when their compression hits it:

```bash
"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless --disable-gpu   --force-device-scale-factor=2 --window-size=<svg-width>,<svg-height>   --default-background-color=FFFFFFFF   --screenshot="$(cygpath -w "$PWD/demo/architecture.png")"   "file:///$(cygpath -m "$PWD/demo/architecture.svg")"
```

The window size must equal the SVG's own `width`/`height`, not the viewBox
scaled up — Chrome renders the SVG at its declared size and pads the rest with
background, so a larger window just adds dead white space. Read the PNG back and
look at it before committing; a diagram that is legible in an editor can still
be unreadable once rendered.

## Repos with no UI

Most repos here have nothing to screenshot. **Do not invent a demo.** For a
library, contract, or infrastructure repo the demo is the *engineering decision*:
show the failure it prevents. A terminal transcript of a test catching real drift
is a better artifact than a fake dashboard, and it is honest.

## Writing rules

- **Concrete beats adjective.** "13 tables, 43 migrations, 100% coverage" earns
  what "robust, production-grade" only claims. Delete every unearned superlative.
- **Lead with the problem**, never the stack. Nobody cares that it uses Delta
  Lake until they know what breaks without it.
- **One sentence, one idea.** Non-technical readers stop at the second comma.
- **Say what it is not.** "This is a portfolio demo on a free tier, not a
  production system" buys more credibility than any claim.
- **No em-dash-heavy consultant prose, no emoji headers, no "unlock", "leverage",
  "seamless", "cutting-edge", "revolutionize".**
- Every technical term gets a plain gloss on first use, in the same sentence.

## The three posts — different platforms, different rules

Write all three in `demo/posts.md`, each ready to paste with no editing.

**LinkedIn** — first person, 150–250 words, no markdown (it renders as literal
asterisks). Hook in the first two lines because the rest is behind "see more".
Lead with the problem or a surprising number. End with a genuine question, not
"thoughts?". 3–5 hashtags maximum, at the bottom.

**Reddit** — the hostile audience, and the most valuable one. Communities like
r/dataengineering punish self-promotion and reward specifics. Lead with the
lesson or the failure, not the project. Include what went wrong and what you
would do differently. Markdown works. No hashtags, no emoji, no "I'm excited to
announce". If the post reads like an announcement, rewrite it as a write-up.

**Discord** — 3–5 lines. Casual, link-forward, one interesting detail. Assume
people are skimming. No hashtags.

All three: **link to the demo or the repo, never to a login wall**, and never
claim the thing is finished if it is not.

## Verification before you report done

- [ ] `bash scripts/secret-scan.sh` passes — posts and demo docs are as public as
      code, and a Tier-2 identifier in a LinkedIn post is still a leak.
- [ ] No AWS account id, workspace host, warehouse id, or ARN anywhere in
      `demo/` or `README.md`.
- [ ] Every claim traced to something real: a released version, a passing test,
      a live URL you fetched. **Do not write "deployed" for something merely
      built.**
- [ ] Every link resolves (`curl -sIL -o /dev/null -w '%{http_code}'`). A dead
      demo link is worse than no link.
- [ ] Non-commercial notice present where the project runs on Databricks Free
      Edition.
- [ ] Nothing in the finance-facing copy reads as investment advice, and any
      heuristic (for example `materiality_band`) is labelled as one.
- [ ] The SVG opens and is legible at 50% zoom, and you have **looked at the
      rendered PNG** — not just confirmed the file exists.
- [ ] `docs/` is unmodified — `git status` proves it.

## What to leave for the human

Say so explicitly in the report rather than faking it: screenshots, a live URL
that does not exist yet, real performance numbers, and anything about the
project's future that is a decision rather than a fact.
