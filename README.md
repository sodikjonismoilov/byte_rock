# byte_rock

A multi-agent system for the Open Agent Hackathon 2026 (Level 2). You type a NYC address, agents investigate whether the building is safe to rent, and the report cites the exact city record behind every claim.

**Deadline:** Tue Oct 27, 2026, 7:45 PM ET.

## Team and roles

| Role | Responsibilities | Branch prefix | Owner |
|---|---|---|---|
| Records Clerk (data and infra) | Zetaris, NYC datasets, Docker | `clerk/` | |
| Squad Captain (agents) | Matcher, Critic, Investigator, Reporter, Nightshift LLM calls | `captain/` | |
| Evidence Keeper (state and front door) | Meterless World Model, run.py, tests | `keeper/` | |

## Rules

- Never commit directly to `main`. Make a branch named `<role>/<what>` (e.g. `keeper/idempotent-ingest`), open a PR, and get one review.
- Never commit API keys. Secrets go in `.env`, which is gitignored.
- No hardcoded outputs. Replays of recorded runs must be labelled as replays.

## Status

- [ ] Zetaris running
- [ ] Agents working on sample data
- [ ] World Model with passing test
- [ ] Nightshift connected
- [ ] Docker build works
- [ ] Demo video
- [ ] Slide deck
- [ ] Submission
