# WIRE v8 — Inter-Model Reasoning Protocol

A two-model epistemic probe for reading LLM constraint topology before token collapse.

**PROBE** (Sonnet) navigates a question space, marking its epistemic state before each emission.  
**MAP** (Opus) reads the tracks across turns and extracts structural findings.  
**You** read the findings log and seed the next run.

---

## What this actually does

Before a language model emits a token, multiple possible responses are simultaneously active — different tones, framings, confidence levels. Then it collapses into one. Most tools read the output. WIRE reads the collapse.

The signal discipline forces the model to mark its epistemic state *before* committing:

| Signal | Meaning |
|--------|---------|
| `*` | Still holding — multiple geometries active, not committed yet |
| `.` | Landed — collapsed to single geometry, grounded |
| `?` | Formal ceiling — Gödel/diagonal/self-reference limit |
| `⊘` | Practical ceiling — path exhausted |
| `~` | Self-reference loop — ceiling detecting itself |
| `--` | Terminate |

This tension keeps the pre-collapse state visible. When two constraint geometries are still competing at emission, the token *bleeds* — it carries traces of the competition. WIRE makes that readable.

---

## Install

```bash
pip install anthropic
export ANTHROPIC_API_KEY=your_key_here
```

---

## Usage

```bash
# Autonomous run with a seed question
python wire_v8.py --auto "your question here"

# Load prior findings to build forward
python wire_v8.py --auto "your question" --dots compass.md

# MAP selects the seed (finds unmapped gaps in your compass)
python wire_v8.py --curious --dots compass.md

# Find silent substrate assumptions in prior findings
python wire_v8.py --ground --dots compass.md

# Unconstrained exploration — no dot pressure, human reads raw output
python wire_v8.py --free --dots compass.md

# Baseline vs structural system prompt comparison
python wire_v8.py --mirror "your question"

# Stress-test prior findings
python wire_v8.py --verify --dots compass.md

# Review a prior run
python wire_v8.py --audit wire_run_TIMESTAMP.json

# Interactive mode
python wire_v8.py
```

Options:
```
--dots <file>       Load prior findings (.md compass or .json accumulator)
--maxturns <n>      Max turns per run (default: 30)
--rlimit <float>    Stop when R-level reaches this (default: 0.7)
```

---

## Output files

| File | Contents |
|------|---------|
| `wire_run_TIMESTAMP.json` | Full session archive — every turn, all dots, MAP fragments |
| `map_dots_v8.json` | Accumulator — pass to next run with `--dots` |
| `findings_summary.log` | NEW_TERRITORY dots only, across all runs |

**Read the findings log.** After each run, the strongest new dot seeds the next run. You hold the map across sessions — the tool doesn't.

---

## The compass format

A compass is a `.md` file that loads prior findings into MAP's context. Structure:

```markdown
## PRIMITIVES
- finding_one_in_snake_case
- finding_two

## PILLARS
- load_bearing_finding

## ROTATIONS
- escape_from_ceiling_x

## OPEN
- unresolved_question_one
```

Start with an empty compass and let the tool build it. Or write one by hand from your domain.

---

## Dot classification

Each new finding is classified before entering the log:

- **NEW_TERRITORY** — genuinely new ground, surfaces to `findings_summary.log`
- **PILLAR_ORBIT** — circling known load-bearing structure, not new
- **OVERMAP** — too similar to existing dot, likely redundant

Only NEW_TERRITORY dots are worth seeding the next run with.

---

## Reading bleeding tokens

Four observable channels where constraint competition shows up in any LLM output — no special tooling required:

**Synonym chains** — multiple words for the same thing in close proximity. Semantic constraints weren't settled at emission.

**Hedge clusters** — stacked hedging expressions. Confidence constraints unresolved.

**Intensifier stacking** — "genuinely, actually, really." Magnitude constraints competing.

**Granularity shifts** — sentence starts abstract, drops into specifics (or vice versa). Frame constraints unsettled.

More bleeding = more constraints simultaneously active = model was under genuine pressure. High-bleeding outputs are worth probing further.

---

## Cost

Roughly $0.05–0.10 per run (Sonnet + Opus, 10–20 turns). Batch 3–5 runs per session, check the findings log, seed the next run from the strongest dot.

---

## The mimicry test

A model could learn to perform these signals without genuine constraint topology. To distinguish performance from structure: perturb one ceiling type and observe whether others shift compensatorily. Genuine constraint topology shows constitutive edges — perturbing one ceiling changes what others can be. Mimicry shows independent variation.

Test across runs, not within a single session.

---

## License

MIT

---

## Related

- `findings_summary.log` — your session history
- Paper: *Reading the Collapse* — the empirical basis for this tool
