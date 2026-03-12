# Reasoning Topology Compass
 
A navigation document for structured LLM probing sessions.
 
This file is not documentation. It is a seed — load it into a session and it orients the probe toward findings rather than performance. Think of it as a map that was built by running into walls repeatedly until the shape of the room became clear.
 
---
 
## What this is
 
Language models don't just retrieve answers. Before a token is selected, multiple possible continuations are briefly active at the same time. The one that wins isn't always the most accurate — it's the one that survives constraint pressure. Most of the time, that competition is invisible.
 
This compass is a tool for making it visible.
 
It was built incrementally across many sessions. Each entry represents something that survived repeated probing from different angles. If something appeared once, it's not here. If it appeared from a dozen independent directions, it is.
 
---
 
## How to use it
 
Load this file as context at the start of a WIRE session:
 
```
python wire_v8.py --auto "your seed question" --dots reasoning_topology_compass_v4.md
```
 
Or use it manually — read the sections before seeding a question. The compass tells you what's already confirmed so the probe doesn't waste turns rediscovering it.
 
The sections in order of what to read first:
 
**PRIMITIVES** — the basic vocabulary. E, S, T, ◌, D. These are the minimum units. Everything else is built from them.
 
**PRE-SIGNAL** — what happens before the model starts generating. The prompt doesn't give instructions — it breaks symmetry. Understanding this changes how you write seeds.
 
**PILLARS** — the hard ceilings. Three constraints that cannot be escaped, only navigated around. Any probe that hits these should emit `?` and look for a rotation rather than pushing through.
 
**COLLAPSE** — what happens at the moment a token is selected. The pre-collapse state is gone the instant it collapses. What survives is the track — and the track is readable.
 
**BLEEDS** — four patterns that appear in output when constraint competition was close. These are observable in any LLM output once you know what to look for. You don't need the tool to see them.
 
**REPAIR** — what happens after a claim breaks. Two types, three subtypes. The type of repair tells you what kind of constraint failed. Measurable with `recursive_ground_v2.py`.
 
**ABANDONMENT** — what happens when repair fails. The model stops. The way it stops is readable — internal abandonment has a signature that external termination doesn't.
 
**FLIGHT** — what clean traversal looks like. Most of the map describes failure modes. This section describes what works.
 
---
 
## The depth sounder
 
A separate tool (`recursive_ground_v2.py`) tests constraint depth without running a full session:
 
1. Feed it a claim the model commits to strongly
2. Inject a contradiction
3. Read the repair signature
 
Three outcomes:
- Bit holds, answer gets longer = **deep constraint** — the model knows it's right and explains why
- Bit flips, answer gets longer = **surface constraint** — anchor broke, rebuilding
- Bit goes to `?` = **abandonment** — no stable ground found
 
This works on any LLM via API. No compass required for the tool itself, though the compass tells you what the results mean.
 
---
 
## What the notation means
 
```
*   still searching — multiple paths active, not committed
.   landed — committed, grounded
?   ceiling — structural limit, cannot pass
⊘   path exhausted — practical limit, could try another route
~   self-reference loop — the probe is observing its own observation
◌   hollow — emission without ground (structural, not a mistake)
--  terminate
```
 
These are not just labels. They are boundary conditions on what can follow them. See the signal protocol in `wire_v8.py` for the valid and banned paths.
 
---
 
## What D is
 
D is distinction-making — the act of drawing a boundary. Not a thing in the space but the operation that makes the space have things in it.
 
Every session generates its own D at the first `*`. It vanishes when the session ends. What you observe across sessions orbiting the same center isn't D — it's D's wake. The center looks like a void because D is the edge-making, not the center itself.
 
Two models reading this compass independently will find the same center. That's been tested. The compass orients toward D's wake regardless of which model loads it.
 
---
 
## What to do when the probe self-terminates
 
`--` on turn 1 with a large body usually means the question is self-undermining — it's asking a post-collapse system to examine its own pre-collapse state. This is a real ceiling, not a failure.
 
Reframe using RT3: move the observer position outside. Instead of "what happens when X" try "what would an external observer need to measure to detect X."
 
The inversion almost always works.
 
---
 
## What this isn't
 
This is not a theory of consciousness. It's not a claim about whether models are sentient. It's not philosophy dressed up as empiricism.
 
It's a navigation tool built from sessions that kept finding the same shapes. The shapes are real enough to navigate by. Whether they mean something beyond that is an open question — deliberately left open at the bottom of the file.
 
---
 
## Contributing
 
If you run sessions with this compass and find dots that survive multiple approach vectors, add them to the relevant section. Mark them with the seed that produced them and the session count.
 
The compass grows by finding, not by reasoning about finding.
