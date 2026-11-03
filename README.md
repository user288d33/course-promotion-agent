# Course Promotion Agent (zero-cost MVP)

A small, multi-project marketing agent scaffold for Pedro Portugal's public Udemy catalog. It matches a learner need to the closest course, finds public questions that reveal demand, prepares useful brand posts, and can publish to a separate Bluesky brand account through its documented API.

**No account is connected and publishing is off by default.** The project does not use browser automation or control your computer. It runs locally on demand or as a scheduled GitHub Actions workflow after you place it in a public GitHub repository and configure that repository.

## What is included

- `data/catalog.json`: 14 publicly listed courses with outcomes, audiences, prerequisites, keywords, and course URLs.
- `data/channels.json`: initial no-cost channel fit/rule directory, with source links and automation status.
- `data/playbook.json`: positioning, sales principles, and non-spam rules.
- `agent.py`: standard-library-only course matching, public question scouting, content drafting, optional Gemini semantic course selection/content generation, and Bluesky publishing.
- `.github/workflows/scout.yml`: weekly scouting and optional daily publishing, gated behind a repository variable.

## Use it

Requires Python 3.11+ and no packages.

```powershell
python agent.py match "I need to troubleshoot short shots and warping in an injection molded part"
python agent.py scout --days 14 --out work/leads.json
python agent.py channels --need "I teach mechanical design and machine components"
python agent.py draft --need "I need to choose a polymer for a hot automotive enclosure" --out work/draft.json
```

`match` prints the best-fit course and alternatives with reasons, plus matching channel options. With a Gemini key configured, it semantically compares the learner need to the catalog; otherwise it uses transparent keyword/outcome scoring. An uncertain or unsupported match does not get a pitch. `channels` ranks known free/organic outlets and shows whether automation is implemented, manual, conditional, or prohibited. `scout` searches public Stack Exchange questions for engineering needs, then routes each through deterministic course matching. These sites are **research signals only**: the agent does not advertise in answers, comments, or direct messages there. The scheduled publisher uses recent questions only as topic signals, then writes a separate post on your brand feed from course facts; it does not reply to, quote, or link back to the source discussion. `draft` makes an educational, brand-oriented post for the chosen course. Without a model API key, it uses fixed, factual templates.

### Optional AI generation without a paid API

The agent supports Google's currently listed Gemini free-tier API, but does not call it unless configured. Free tiers and terms can change; do not attach billing for a strict $0 setup. If the quota is exhausted, generation fails closed and the agent uses a local factual template. Free-tier requests may be used by Google to improve its products, so send only public course facts and campaign context—not secrets or private learner/customer data.

Set `GEMINI_API_KEY` as an environment variable or GitHub Actions secret. Optional `GEMINI_MODEL` defaults to `gemini-3.6-flash-lite`; model availability may change. This uses a hosted model with your course knowledge base; it does **not** train model weights. The catalog and playbook specialize the agent through context, and outcome data can later improve the playbook and evaluations. A separately fine-tuned model can be considered if you have a legally usable set of examples and free compute.

### Optional brand publishing (Bluesky)

Create a dedicated brand account, then create an **app password** for it in Bluesky. The workflow supports text posts with a course link. Store these as repository secrets, never in files:

- `BSKY_HANDLE`
- `BSKY_APP_PASSWORD`

To enable unattended posting after reviewing drafts, add a repository variable `AUTO_PUBLISH` with value `true`. Scheduled jobs publish at most one post per UTC day and skip if the brand account already posted that day. Leave this variable unset/false for research-only operation. Manual workflow runs can accept a learner need, match it to a course, and return a draft artifact; they never publish. The Bluesky account must represent your brand publicly; a human account owner may still be required to create/administer it.

## Free background setup

1. Create a **public** GitHub repository and upload this folder's contents. A public repo is required for GitHub Actions to be free under the current plan. Keep the catalog and code public; keep credentials only in GitHub Secrets.
2. Enable Actions. The weekly scout produces a downloadable JSON artifact with candidate questions, fit scores, and source links. A manual run can also accept a learner need and create a reviewable post draft.
3. Review the repo's `data/catalog.json` and `data/playbook.json`; replace the provisional brand name when known.
4. Create the separate Bluesky brand account and add its app-password secrets only if you want the account connected.
5. First leave `AUTO_PUBLISH` unset. Run the workflow manually with a sample learner need and inspect the draft artifact. Turn posting on only after reviewing drafts and the destination account.
6. To use AI, add a no-billing Gemini API key only if the provider offers a free tier for your account. Disable it to run deterministic matching and templates only.

GitHub schedules can be delayed. No model/API free tier or platform policy is guaranteed permanently. There is no paid fallback in this code. Publishing does not include paid ads, DMs, replies to unrelated users, or automation on community Q&A sites.

## Sales logic

The agent's sales goal is an honest course recommendation, not maximum posting volume. It first identifies the learner's problem, ranks courses by explicit topic/audience/outcome overlap, and declines to pitch if the fit is weak. Drafts state a practical learning benefit, one useful tip, the relationship to the course, and a relevant next step. It must not invent scarcity, discounts, outcomes, credentials, or testimonials. The routing examples in `data/playbook.json` are synthetic teaching examples, not customer evidence or testimonials. `data/outcomes.csv` is a manual place to record channel results; Udemy sales data is not connected in this MVP.

The included account label is provisional: `Practical Engineering Learning`. Change it in `data/playbook.json` to match the brand account before posting.

## Sources checked 2026-11-02

- Udemy profile and catalog pages linked in `data/catalog.json`.
- GitHub Actions free public repository details: https://github.com/pricing
- GitHub Actions limits and schedules: https://docs.github.com/en/actions/reference/limits
- Bluesky post creation: https://docs.bsky.app/docs/tutorials/creating-a-post
- Gemini API free tier and data-use notes: https://ai.google.dev/gemini-api/docs/pricing
- Stack Exchange API: https://api.stackexchange.com/docs
- Udemy community self-promotion restrictions: https://community.udemy.com/en/discussion/9355/self-promotion-policy-in-the-udemy-community/p1

