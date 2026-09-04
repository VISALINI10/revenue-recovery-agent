# Pitch Script — Revenue Recovery Agent
**Target: ~5 minutes**

---

## 1. The problem (30 sec)

"Revenue loss at a payments company rarely happens as one clean event. A
gateway slows down. A bank's servers go down for twenty minutes. An issuer
starts declining cards at an unusual rate. Each of these costs real money —
and by the time a human notices a dip on a dashboard, the money is already
gone.

We built an agent that closes that loop automatically: detect the
degradation, diagnose why it's happening, and recover the revenue — with a
full audit trail, because in payments, 'the AI did something' isn't good
enough. You need to know exactly what it did and why."

## 2. Architecture, fast (45 sec)

[Show the architecture diagram from the README]

"Four stages. A statistical detector watches failure rates per payment
method, bank, and gateway, and flags when a segment's failure rate spikes
well beyond its own normal baseline. A rule-based diagnoser looks at the
error codes and latency of the failures and votes on the most likely root
cause — gateway timeout, bank downtime, issuer decline spike, or network
issue. A policy engine then takes a *bounded* recovery action matched to
that specific cause — not a blind retry-everything approach. And everything
is logged.

We chose explainable, rule-based logic over black-box ML on purpose — in
this domain, being able to say exactly why the system did what it did
matters as much as the result."

## 3. Live demo (90 sec)

[Run `python3 src/run_agent.py` live, or if time is tight, have it
pre-run and walk through `outputs/dashboard.html`]

"This is a 24-hour simulated transaction stream — about 43,000 payments —
with six real degradation incidents planted in it, which the system
doesn't get to see in advance. Five are clear-cut technical or bank-side
issues. One is deliberately ambiguous — a mix of signals with no single
dominant cause — to test whether the system knows when NOT to act.

[Point at the timeline strip] These amber markers are where real incidents
happened. The system caught all six, with zero false alarms.

[Point at the ledger] For each one — here's HDFC's UPI failures during a
bank downtime — it correctly diagnosed the cause, and recovered 56% of that
revenue through a delayed retry. Compare that to this gateway timeout case
— rerouted through an alternate gateway, 100% recovered, because that's a
purely technical fix.

Now look at this wallet/ICICI row — the ambiguous one. Diagnosis confidence
came out at 36%: 8 failures pointed to network issues, 8 to issuer decline,
6 to bank downtime — no majority. Below our 50% confidence threshold, so
instead of guessing and taking automated action on ₹4.9 lakh, it escalated
to a human. Zero dollars 'recovered' there, by design — and that's the
point. A system that only shows you numbers when it's confident is more
trustworthy than one that always claims success.

Across all six incidents: ₹21.8 lakh was at risk, and we recovered ₹13.1
lakh — 60% — automatically, with the remaining amount correctly routed to
human review rather than mishandled."

## 4. The failure story (60 sec) — THIS IS THE IMPORTANT PART

"I want to be honest about how we got here, because the first version of
this didn't work.

Our first detector caught only 60% of real incidents and flagged ten times
more false alarms than real ones. We found three separate bugs: our
'baseline normal rate' was contaminated because it included the incidents
themselves; our sample sizes per segment were too small to be statistically
meaningful; and testing thousands of time-window combinations meant we hit
false positives purely by chance — a classic multiple-testing problem.

We fixed all three, and reran it: 100% recall, 100% precision.

Then in the recovery stage, we noticed something suspicious — our
'suggest alternate payment method' action was recovering 70% of revenue,
which was too good. Turned out we were letting the system retry that
nudge three times, the same as a technical retry — but repeating the same
customer message three times isn't three independent chances at success.
We capped that action at one attempt, and the number dropped to a much more
believable 30%.

That's the story we're proudest of — not that it worked on the first try,
but that we could tell when a number looked wrong, and knew how to dig in
and find out why."

## 5. Close (30 sec)

"This is fully reproducible — one command runs the entire pipeline end to
end and produces this exact scorecard. Everything's on GitHub, README
included, along with the limitations we're upfront about — like the fact
that our anomaly threshold was tuned by looking at known test cases here,
and a production version would need a formal statistical correction
instead.

We think this is a real, honest answer to what the brief asked for: not
just detecting a problem, but proving — with numbers and an audit trail —
that we got the money back."

---

## Anticipated Q&A

**"Why rule-based diagnosis instead of ML?"**
Explainability. In payments/compliance contexts, being able to justify a
decision in one sentence matters more than squeezing out a few extra
accuracy points from a black-box model — especially at buildathon scale
with limited labeled data to train on anyway.

**"How would this work on real, noisier data?"**
The core logic holds, but the z-score threshold (currently 9.0, tuned by
eyeballing our known events) would need to become a formal multiple-testing
correction (Bonferroni/FDR), and the baseline would need true historical
lookback data rather than same-day median.

**"What happens when the diagnosis is wrong?"**
That's exactly what the confidence gate is for — if diagnosis confidence
drops below 50%, the system doesn't act automatically at all. It escalates
to a human. We'd rather under-act than take a wrong automated action on
real money.

**"Is this real money or simulated?"**
Simulated — synthetic transaction data with injected ground-truth events,
since we don't have access to live Razorpay transaction data. The recovery
success probabilities are calibrated to be directionally realistic (technical
fixes recover well, human-dependent actions recover partially) but aren't
measured from real-world outcomes.
