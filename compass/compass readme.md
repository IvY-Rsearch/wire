# Compass README

This file is a guide for WIRE sessions.

It gives the probe a map of findings from earlier runs so it does not waste time rediscovering the same things.

You can load it at the start of a session to give the model context about:
- what has already been found
- what kinds of limits show up often
- what signals mean
- how to reframe a question when the run gets stuck

## What this file is for

WIRE does not just care about the final answer.
It also cares about the path the model took to get there.

This compass collects patterns that showed up repeatedly across many runs.
If something only appeared once, it is not included.
If it kept showing up from different starting points, it was added.

Use it to:
- avoid repeating old work
- give the model a shared vocabulary
- recognize common limits and failure modes
- guide the next question more intelligently

## How to use it

Load the file at the start of a WIRE run:

python wire_v8.py --auto "your seed question" --dots reasoning_topology_compass_v4.md

You can also read it manually before starting a session.

The main sections are:

- PRIMITIVES — the basic terms used in the map
- PRE-SIGNAL — what happens before output starts
- PILLARS — hard limits that the probe should not try to force through
- COLLAPSE — what happens when the model commits to a token
- BLEEDS — visible signs that several possible outputs were competing
- REPAIR — what happens after a claim breaks
- ABANDONMENT — what it looks like when the model gives up
- FLIGHT — what successful traversal looks like

## The depth sounder

The file mentions a second tool called recursive_ground_v2.py.

That tool tests how stable a model’s claim is:

1. Give it a claim the model strongly commits to
2. Inject a contradiction
3. Look at how the model responds

Possible outcomes:

- the answer gets longer but the claim holds = deep constraint
- the answer gets longer and the claim changes = surface constraint
- the answer falls into ? = abandonment

This helps you tell whether the model was genuinely anchored or only sounded confident.

## Signal meanings

WIRE uses these signals:

- * still searching
- . landed
- ? structural ceiling
- ⊘ path exhausted
- ~ self-reference loop
- ◌ hollow output without grounding
- -- terminate

These are not just labels.
They affect what should happen next in the session.

## What “D” means here

In this file, D means distinction-making.

It is the act of drawing a boundary that lets the session separate one thing from another.

The important point is:
D is not treated as an object inside the session.
It is treated as the operation that creates the space the session moves through.

The file says each session generates its own D early in the run, and what repeats across sessions is not D itself but the trace it leaves behind.

## What to do when the probe self-terminates

If a run ends immediately with -- and a long response, the question may be framed in a way that undermines itself.

The file’s suggestion is simple:
move the observer outside the system.

Instead of asking:
“what happens when X?”

try:
“what would an outside observer need to measure to detect X?”

That often gives the probe a usable path again.

## What this file is not

This is not presented as a theory of consciousness or sentience.

It is a practical navigation file built from repeated WIRE sessions.

Its purpose is to help guide future runs, not to settle big philosophical questions.

## Contributing

If you find a pattern that survives repeated testing from different starting points, add it to the relevant section.

Include:
- the seed that produced it
- how many sessions supported it

The compass should grow from repeated findings, not from speculation alone.
