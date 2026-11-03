# Start here

This is the first working version of the promotion agent. It already knows 14 courses from your public Udemy catalog and has routing examples for common learner needs.

## What it can do

- Match a learner's engineering need to the most relevant course.
- Decline to pitch when the fit is weak.
- Scout recent public engineering questions for topic demand.
- Rank likely promotion channels and surface the rules and automation status for each.
- Write a standalone educational post for your brand account, using the selected course link.
- Publish at most one post per UTC day to a dedicated Bluesky account after you enable it.

It does not post to your personal accounts. It never posts promotional answers, comments, or DMs in the communities it scouts.

## Free setup path

1. Create a free **public GitHub repository** and upload the contents of this folder. GitHub currently lists Actions as free for public repositories. Keep all code and course facts public; never put passwords or API keys in files.
2. Enable GitHub Actions for the repository.
3. In Actions, run **Course promotion agent** manually. Enter a sample need such as “How do I troubleshoot warping in injection molding?” The run scouts public questions and gives you a downloadable draft artifact. Manual runs cannot publish.
4. For AI semantic matching and writing, create a Gemini API key with a free tier, do not link billing, and add it as repository secret `GEMINI_API_KEY`. Free-tier availability and limits can change. Gemini's free-tier terms say submitted content may be used to improve Google products; this agent sends only public course information and campaign text.
5. Create a separate Bluesky brand account (provisional name: `Practical Engineering Learning`; edit `data/playbook.json` if needed). In Bluesky account settings, create an app password. Add repository secrets `BSKY_HANDLE` and `BSKY_APP_PASSWORD`.
6. Review several manual draft artifacts. Only when you're ready for unattended publishing, add repository variable `AUTO_PUBLISH` with value `true`. The daily schedule then scouts current topic signals and publishes one post to the brand account. Delete or change that variable to stop publishing.

Do not add billing to the AI project or a paid social scheduler if the budget must remain exactly $0. If the free AI quota is missing or exhausted, the agent falls back to its deterministic matcher and factual post templates. GitHub schedules can be delayed and free quotas can change.

## What still needs a human account owner

Creating the public GitHub repository, brand account, and secrets requires account access. Those accounts are not connected in this workspace, so no live account has been created or posted to. The public brand label is currently `Practical Engineering Learning`; change it in `data/playbook.json` before posting if you prefer a different name.

## Files to update as the business grows

- Add courses and projects to `data/catalog.json`.
- Add reviewed channels and policy/source links to `data/channels.json`.
- Add verified answers and routing examples to `data/playbook.json`.
- Record views, clicks, enrollments, and refunds in `data/outcomes.csv`. Udemy sales analytics are not connected automatically in this version.
- Do not create synthetic testimonials or train on identifiable student/customer information.

