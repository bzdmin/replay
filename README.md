# Replay

**Rehearse a change before you ship it.**

Every production change carries consequences that aren't visible in the diff.
Replay takes a proposed change in plain language, works out what it can reach,
designs behavioural scenarios, **actually executes them against the current and
the proposed code**, compares the real observed results, and then has a separate
agent try to prove that conclusion wrong.

Built with the [Strands Agents SDK](https://strandsagents.com) on AWS.

| | |
|---|---|
| **Live** | <https://replay-aj3d.onrender.com> (no login; three real recorded rehearsals open instantly) |
| **Proof without a model** | `/api/proof` recomputes **12 real executions** of the demo scenarios on request, in about 1 second on a laptop and about 3 on the free hosting tier, with no agents and no spend. The numbers on the page were produced while you were reading it. |
| **Track** | AWS Agents for Humans Hackathon, Professional Agents |
| **Measured** | The recorded fee rehearsal: **11 scenarios, 22 real executions, 6 predictions contradicted**. The legacy rehearsal: 9 scenarios, 18 executions, 1 contradicted. The rounding rehearsal: 11 scenarios, 22 executions, **0 contradicted, and the verifier still refused to pass it**. A rehearsal costs about **$0.58** in Bedrock tokens (79,103 in, 7,297 out). |
| **Honest limit** | Pointed at its own source, Replay discarded **6 of the 9** scenarios it generated because it could not execute them, and said so instead of inventing findings. |

---

## Why this is not change-impact analysis

Existing tools answer *"what might be affected?"* Replay answers *"what actually
behaved differently, and does that break a rule?"*

The difference is that Replay runs an experiment. Scenarios execute as real
subprocesses inside isolated copies of the repository - one pristine, one with
the change applied. If Replay claims behaviour changed, there is an execution
trace behind the claim.

## Architecture

![Replay architecture](docs/architecture.png)

| Component | Kind | Job |
|---|---|---|
| Impact Agent | Strands agent | Traces what the change reaches, including duplicates the diff misses |
| Scenario Agent | Strands agent | Designs the observations that would expose a difference |
| Replay Runner | deterministic | Executes every scenario in both sandboxes, captures real output |
| Verifier Agent | Strands agent | Adversarial - tries to prove the conclusion wrong |

The Replay Runner is deliberately **not** an agent. Executing a scenario and
comparing two outputs is deterministic work; wrapping it in a model would add
cost and a failure mode while removing the guarantee that makes the rest
credible.

## Setup

Requires Python 3.11+, and AWS credentials with Amazon Bedrock model access.

```bash
pip install -r requirements.txt
```

**1. Model access.** Nothing to do in most accounts - serverless foundation
models are enabled automatically on first invocation, and the old Bedrock
"Model access" console page has been retired. First-time users of Anthropic
models may be asked to submit use-case details once before the first call
succeeds.

**2. Provide credentials.** Either via `aws configure`, or environment variables:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1
```

**3. Optional tuning.**

| Variable | Effect |
|---|---|
| `REPLAY_ECONOMY=1` | Runs the Impact and Scenario agents on Claude Haiku 4.5 to cut spend. The Verifier always stays on the strongest model. |
| `REPLAY_MODEL_PREFIX=us.` | Use regional inference profiles, if Bedrock rejects the plain model id. |
| `AWS_REGION` | Bedrock region (default `us-east-1`). |

## Running it

**Check your setup first.** This verifies credentials, region, and that Bedrock
will actually answer - and names the exact problem if not:

```bash
python scripts/check_aws.py
```

**The web interface** - the same thing the live demo runs:

```bash
uvicorn replay.web:app --host 0.0.0.0 --port 8000
```

Then open <http://localhost:8000>. The page loads a previously recorded
rehearsal immediately. Each of the three presets opens its own recorded run
straight away, and you can type your own change to run a live one and watch the
agents work.

**A rehearsal from the command line:**

```bash
python scripts/rehearse.py "Change the standard transaction fee from 2.5% to 2%"
```

**The deterministic harness on its own**, with hand-written scenarios and no
model calls - useful for verifying the sandbox works without spending anything,
and for seeing that the before/after evidence is real:

```bash
python scripts/demo_rehearsal.py
```

**Re-record the runs** shown on the web page. The first is the one shown on
first paint; `--out` writes the others alongside it instead of overwriting it:

```bash
python scripts/record_run.py
python scripts/record_run.py --out legacy "Move legacy-enterprise merchants onto the modern billing path"
python scripts/record_run.py --out rounding "Change money rounding from ROUND_HALF_UP to ROUND_DOWN"
```

### Live rehearsals are rate limited

A rehearsal costs about **$0.58** in Bedrock tokens, measured from the agents'
own usage metrics. A public URL making real model calls is a fast way to lose a
credit balance, so `replay/web.py` caps live runs: one at a time, a 45 second
per-client cooldown, 30 per hour, and a lifetime spend ceiling denominated in
dollars rather than runs (`REPLAY_SPEND_BUDGET_USD`, default 40). When a cap is
hit the page says so and the recorded run stays on screen.

## Deploying it

Replay ships a `Dockerfile` and reads its port from `$PORT`, so the same image
runs on Hugging Face Spaces, Fly, Cloud Run, ECS, or a laptop.

**Render**, which is what the live demo runs on:

1. New Web Service, connect this repository, runtime **Docker**
2. Health check path `/healthz`, plan **Free**, a **US region** so the app sits
   near the Bedrock region rather than a transatlantic hop away
3. Add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as environment variables.
   The container needs its own credentials; it cannot use yours.

`render.yaml` carries this configuration for the Blueprint flow.

Scripts for two other targets are included: `scripts/deploy_cloudrun.sh` for
Google Cloud Run, which gives a full vCPU on its free tier, and
`scripts/deploy_space.sh` for Hugging Face Spaces, which now requires a paid
plan for Docker.

**Keeping it warm.** Free hosting sleeps after about fifteen minutes idle, and a
cold start costs a visitor the best part of a minute.

Use an external uptime pinger against `/healthz` every five to ten minutes.
UptimeRobot and cron-job.org both do this free, and an uptime monitor also tells
you when the demo is down, which matters if people are looking at it while you
are not.

`.github/workflows/keep-warm.yml` does the same thing on a schedule, but treat
it as a backup rather than the mechanism: GitHub deprioritises scheduled
workflows on free repositories, and a `*/10` schedule was measured running five
times in eighteen hours. Set the repository variable `DEMO_URL` to the deployed
base URL under **Settings -> Secrets and variables -> Actions -> Variables**.

## The demo repository

`demo-repo/acmepay` is a small payments application with a deliberately
realistic problem. The transaction fee is defined once in `core/config.py` - but
`services/legacy_billing.py`, ported from a mainframe, holds its own copy as
`_FEE_BASIS_POINTS = 250`. A search for `0.025` or `STANDARD_FEE_RATE` never
finds it.

Meanwhile `docs/business-rules.md` BR-207 states that the refund fee is
*contractually fixed* at 2.5% and does not track the standard fee - but
`services/refund_service.py` imports `STANDARD_FEE_RATE` anyway.

So a one-line config change produces two failures of opposite kinds: a
divergence that should not have happened, and a non-divergence that should have.

The repository also ships two more rehearsals, each with its own recorded run
on the live site at `/#legacy` and `/#rounding`.

**Moving legacy-enterprise merchants onto the modern billing path** looks like
a safe migration. It moves the fee on a $99.99 charge from 2.49 to 2.50,
because the legacy engine truncates and the modern path rounds - two
implementations of the same rule that have never had to agree before. The
verifier rates it high risk under BR-310, the same rule that keeps those
merchants on the legacy engine in the first place.

**Changing money rounding from ROUND_HALF_UP to ROUND_DOWN** is the opposite
case. All eleven scenarios behave exactly as predicted, and the verifier still
says do not ship it, because four separate contractual rules - BR-101, BR-207,
BR-310 and BR-415 - depend on how that rounding behaves. A change can be
entirely predictable and still be forbidden.

## Layout

```
replay/
├── sandbox.py     isolated copies, edit application, subprocess execution
├── scenarios.py   Scenario / Edit / Change / ScenarioResult
├── differ.py      before-vs-after classification
├── tools.py       Strands tools for investigating a repository
├── agents.py      the three agents and their structured outputs
├── pipeline.py    the rehearsal pass, end to end
└── _driver.py     dependency-free, runs inside the sandbox
```

## License

Licensed under the **Apache License, Version 2.0**. See [LICENSE](LICENSE) for
the full text.

You may obtain a copy of the License at
<http://www.apache.org/licenses/LICENSE-2.0>.
