## Inspiration

Payment failures rarely happen as one clean, obvious event. A payment
gateway slows down. A bank's servers go down for twenty minutes. A card
issuer starts declining transactions at an unusual rate. Every platform
that processes online payments — a business, a college fest's ticketing
system, a student marketplace app — loses real revenue to exactly this
kind of silent failure, and by the time someone notices a dip on a
dashboard, the money is already gone and the cause is cold. We wanted to
see if that entire loop — noticing, understanding, and recovering — could
be closed automatically, without turning into a black box nobody could
trust with real money.

## What it does

Revenue Recovery Agent is an autonomous pipeline that:

1. **Detects** payment degradation in near real time — a statistical
   monitor watches failure rates per payment method, bank, and gateway,
   and flags when a specific segment's failure rate spikes well above its
   own normal baseline.
2. **Diagnoses** the root cause — a rule-based classifier reads the failed
   transactions' error codes and latency patterns and votes on the most
   likely cause (gateway timeout, bank downtime, issuer decline spike,
   network issue), producing both an answer and a confidence score.
3. **Recovers** the revenue with a *bounded* action matched specifically
   to that cause — rerouting a technical failure through an alternate
   gateway, delaying and retrying for a bank outage, nudging the customer
   toward an alternate payment method for a likely-genuine decline. Every
   action has hard stopping rules (capped retries, cooldowns) — and if the
   diagnosis confidence is too low, the system escalates to a human
   instead of guessing.
4. **Proves** it worked — every detection, diagnosis, and recovery attempt
   is logged to a full audit trail, so nothing the system does is a black
   box.

We validated it end-to-end against a synthetic 24-hour transaction stream
(~43,000 payments) with six known degradation incidents secretly planted
in it. The system achieved 100% detection recall and precision, 100%
diagnosis accuracy, and recovered 60% of at-risk revenue automatically —
correctly escalating the one deliberately ambiguous incident to a human
instead of guessing.

## How we built it

The pipeline is Python (pandas/numpy), structured as four sequential
stages orchestrated by a single entry-point script: `generate_data.py` →
`detector.py` → `diagnoser.py` → `recovery_engine.py`, plus a
self-contained HTML/CSS dashboard for visualizing results.

We deliberately chose explainable, rule-based and statistical methods over
black-box machine learning at every stage:

- **Detection** uses a rolling-window two-proportion z-test comparing each
  segment's current failure rate against its own historical baseline —
  not a trained anomaly-detection model, since we had no labeled incident
  data and needed every flag to be justifiable in one sentence.
- **Diagnosis** uses a majority-vote over error codes, cross-checked
  against latency for consistency, rather than a trained classifier.
- **Recovery** uses a fixed policy table (root cause → bounded action)
  rather than a learned/reinforcement-learning policy, because taking a
  wrong automated action on real payments has real consequences — we
  didn't want a system "learning" that on live traffic.

To test it honestly, we generated our own synthetic transaction data with
known ground-truth incidents secretly injected — five clear-cut, and one
deliberately ambiguous (mixed error signals, no dominant cause) to
specifically test whether the system knows when *not* to act confidently.

## Challenges we ran into

Getting this right took real, iterative debugging — not a clean first
pass.

**Detection was badly broken at first.** Our first version caught only
60% of real incidents while generating ten times more false alarms than
true ones. We traced this to three separate bugs: our "normal" baseline
failure rate was contaminated because it was computed from data that
included the incidents themselves; our per-segment sample sizes were too
small to be statistically meaningful; and testing thousands of
segment/time-window combinations created a multiple-testing problem where
false positives occurred by chance alone, even at a strict-looking
threshold. We fixed each — a robust median-based baseline, higher
transaction volume, and a persistence + statistically-justified threshold
— and reached 100% recall and precision.

**Recovery logic had a subtler bug.** Our engine initially let every
recovery action retry up to three times uniformly. This inflated our
"suggest alternate payment method" action's simulated recovery rate to a
suspicious 70% — but retrying the exact same customer nudge three times
isn't three independent chances at success the way a technical retry is.
We made retry limits action-specific, and the number dropped to a far
more believable 30%.

**A bug our own diagnoser caught.** The diagnoser cross-checks latency
against its claimed root cause as a sanity check. It flagged one genuine
event with only 70% confidence because the latency didn't match — which
led us to discover a naming bug in our own synthetic data generator (one
bank-downtime error code wasn't tagged for high latency like its sibling
code was). Fixing the generator brought that event's confidence to 100%.

## Accomplishments that we're proud of

- **100% detection recall and precision, 100% diagnosis accuracy**,
  measured against a real, known answer key — not just plausible-looking
  output.
- **A system that knows when not to act.** The confidence-gated escalation
  path is the accomplishment we're most proud of: when diagnosis
  confidence on our deliberately ambiguous test event came out at just
  36%, the system correctly refused to auto-act on ₹4.9 lakh and escalated
  to a human instead. A system that only claims success when it's actually
  confident is more trustworthy than one that always says it worked.
- **Catching our own mistakes rather than hiding them.** Multiple times
  during the build, a suspiciously good-looking number turned out to be a
  real bug, and we traced each one back to its actual root cause instead
  of just re-tuning until the output looked nice.

## What we learned

- **Explainability is a design constraint, not an afterthought.** Choosing
  statistical/rule-based methods over ML from the start meant every single
  decision the system made could be justified in one sentence — which
  mattered far more once we were building the audit trail and confidence
  gating than raw predictive power would have.
- **A good-looking number is a reason to dig deeper, not stop.** Several
  of our biggest bugs were hiding behind results that looked fine at first
  glance (a 70% recovery rate, a "detected" event) until we checked them
  against ground truth or basic sanity logic.
- **The multiple-testing problem is easy to miss and easy to create.**
  Running one statistical test is simple to reason about; running
  thousands of them (across many segments and time windows) silently
  changes the odds of a false alarm, and we had to explicitly account for
  that rather than trusting a single-test threshold.

## What's next for Revenue Recovery Agent

- Replace the empirically-tuned detection threshold with a formal
  multiple-testing correction (Bonferroni or false-discovery-rate control)
  so it doesn't rely on having seen known incidents in advance.
- Validate against real (anonymized) transaction data instead of synthetic
  data, to test the pipeline against noisier, less clean real-world
  failure patterns.
- Extend the diagnoser to detect correlated failures across multiple
  related segments at once (e.g., a bank going down affecting several
  payment methods simultaneously), rather than treating each segment
  independently.
- Build a lightweight live-monitoring mode (rather than batch analysis) so
  the agent could run continuously against a real transaction stream.
