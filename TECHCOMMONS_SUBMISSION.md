# TechCommons Hacks V2 — Submission Text

---

## Project Name

**Revenue Recovery Agent**

## Short Description (1-2 sentences, for the form's summary field)

An autonomous agent that detects payment failures in real time, diagnoses
why they happened using explainable rule-based logic, and automatically
recovers the lost revenue with a bounded, auditable action — or escalates
to a human when it isn't confident enough to act safely.

---

## Full Project Description (Problem / Solution / How Built / Impact)

### The Problem

Whenever a platform processes online payments — a business, a college
event's ticketing system, a student marketplace app — payment failures
happen constantly, and rarely as one clean, obvious event. A payment
gateway slows down. A bank's servers go down for twenty minutes. A card
issuer starts declining an unusual number of transactions. Each of these
silently costs real money, and by the time a human notices a dip on a
dashboard, the money is already gone and the cause is cold. Most teams
handle this reactively — someone eventually notices, digs through logs,
and manually decides what to do. That delay is where the revenue is lost.

### The Solution

Revenue Recovery Agent closes that loop automatically, in four stages:

1. **Detect** — A statistical monitor watches failure rates per payment
   method, bank, and gateway, flagging when a segment's failure rate spikes
   significantly above its own normal baseline (using a rolling-window
   two-proportion z-test).
2. **Diagnose** — For each flagged incident, a rule-based classifier looks
   at the failed transactions' error codes and latency patterns and votes
   on the most likely root cause (gateway timeout, bank downtime, issuer
   decline spike, network issue), producing both an answer and a
   confidence score.
3. **Recover** — A policy engine takes a *bounded* action matched
   specifically to that root cause — rerouting a technical failure through
   an alternate gateway, delaying and retrying for a bank outage, nudging
   the customer toward an alternate payment method for a likely-genuine
   decline. Every action has hard stopping rules (capped retry attempts,
   cooldowns), and critically, if the diagnosis confidence is too low, the
   system escalates to a human instead of guessing.
4. **Prove** — Every single decision, attempt, and outcome is logged to a
   full audit trail, so the system's behavior is always explainable and
   verifiable after the fact — not a black box.

### How We Built It

The pipeline is Python-based (pandas/numpy), built as five sequential
stages orchestrated by one entry-point script:
`generate_data.py → detector.py → diagnoser.py → recovery_engine.py →
dashboard`. We deliberately chose explainable, rule-based and statistical
methods over black-box machine learning at every stage — a z-score or a
vote-based diagnosis can be justified in one sentence, which matters when
the system is taking automated action on real money.

To validate it honestly, we built a synthetic 24-hour transaction stream
(~43,000 payments) with six known degradation incidents secretly planted
in it — five clear-cut, and one deliberately ambiguous (ambiguous error
signals with no dominant cause) to test whether the system knows when
*not* to act. The system never sees these labels; we only use them
afterward to grade it.

**Getting there took real debugging, not a clean first pass.** Our first
detector caught only 60% of real incidents with ten times more false
alarms than true ones — traced to three separate bugs: a contaminated
statistical baseline (it accidentally included the incidents it was
supposed to detect), sample sizes too small to be statistically
meaningful, and a multiple-testing problem from running thousands of
statistical tests across many time windows and segments. We diagnosed and
fixed each one, reaching 100% recall and precision. Separately, we noticed
our recovery engine's "suggest alternate payment method" action was
recovering a suspiciously high 70% of revenue — because we were letting it
retry three times like a technical fix, when a repeated customer nudge
isn't three independent chances at success. We capped that action's
retries at one attempt, and the number dropped to a believable 30%.

### Impact

Payment failures are a near-universal problem for anything that processes
online transactions, not just large fintech companies — a student
marketplace app, a hackathon's own ticketing system, a small e-commerce
project could all lose a measurable share of revenue to exactly this kind
of silent, undiagnosed failure. This project demonstrates that detecting,
diagnosing, and safely recovering from that failure can be automated
without sacrificing explainability or safety — the system is validated
end-to-end against a known answer key (100% detection recall/precision,
100% diagnosis accuracy) and recovers 60% of at-risk revenue automatically
while correctly routing the remaining, uncertain cases to a human rather
than mishandling them.

---

## Video Script (2-3 minutes — trimmed from the longer version)

**[0:00–0:20] Problem**

"Payment failures rarely happen as one clean event — a gateway slows down,
a bank goes down, an issuer starts declining cards unusually often. By the
time someone notices, the money's already gone. We built an agent that
detects it, figures out why, and recovers the revenue automatically — with
a full audit trail."

**[0:20–0:45] Architecture**

"Four stages: a statistical detector flags abnormal failure spikes per
payment segment. A rule-based diagnoser reads error codes and latency to
figure out the cause. A policy engine takes a bounded action matched to
that cause — reroute, delayed retry, customer nudge, or escalate to a
human if it isn't confident. Every decision is logged."

**[0:45–1:45] Live run + dashboard**

"This is a simulated 24-hour transaction stream with six real incidents
planted in it that the system never sees in advance." [run it / show
scorecard] "All six caught, zero false alarms, all six correctly
diagnosed." [switch to dashboard] "Here's the timeline, and the event
ledger — this bank-downtime case recovered 56% via delayed retry, this
gateway timeout recovered 100% via reroute. And here's the one
deliberately ambiguous case — 36% confidence, no dominant cause — so
instead of guessing on ₹4.9 lakh, it escalated to a human. Zero automated
recovery there, by design."

**[1:45–2:30] The honest build story**

"This didn't work first try. Our first detector caught only 60% of real
incidents with far too many false alarms — three bugs: a contaminated
baseline, too-small sample sizes, and a multiple-testing problem. We fixed
all three and hit 100% recall and precision. We also caught our recovery
engine over-crediting a customer-nudge action by letting it retry three
times like a technical fix — fixed that too."

**[2:30–2:50] Close**

"Everything's reproducible — one command, same result every time, full
source on GitHub. We think this is a genuinely useful, honest answer to a
real problem: not just detecting failure, but proving you got the money
back."
