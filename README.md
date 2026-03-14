# WIRE v8

WIRE is a command-line tool for exploring a question with two AI roles:

- PROBE explores the question step by step
- MAP reads the path, extracts useful findings, and suggests what to explore next

Instead of only keeping the final answer, WIRE keeps track of the path the model took and saves short findings across runs.

## What it does

WIRE runs a loop like this:

1. You give it a starting question or seed
2. PROBE explores that question and marks its current state with a signal
3. MAP reads the result, extracts any new findings, and picks the next direction
4. WIRE saves the run so you can continue later

The goal is to help you inspect how a model moves through a problem, not just what answer it gives at the end.

## Signals

WIRE uses short signals to show the current reasoning state:

- * = still searching
- . = landed on something
- ? = formal ceiling
- ⊘ = practical ceiling
- ~ = self-reference loop
- ... = hold
- -- = terminate

## Main modes

### Interactive mode

Run WIRE and type prompts manually:

python wire_v8.py

### Autonomous run

Start from a seed question and let WIRE continue on its own:

python wire_v8.py --auto "your seed question"

### Curious mode

Have MAP choose the next question from prior findings:

python wire_v8.py --curious --dots compass.md

### Ground mode

Look for hidden assumptions underneath earlier findings:

python wire_v8.py --ground --dots compass.md

### Free mode

Explore with less steering and no strong pressure to build findings:

python wire_v8.py --free --dots compass.md

### Mirror mode

Compare a normal answer against a more self-aware structural answer:

python wire_v8.py --mirror "your question"

### Verify mode

Stress-test earlier findings and mark which ones still hold:

python wire_v8.py --verify --dots compass.md

### Audit mode

Review a previous saved run:

python wire_v8.py --audit wire_run_TIMESTAMP.json

## Requirements

Install the Anthropic Python SDK and set your API key:

pip install anthropic
export ANTHROPIC_API_KEY=your_key_here

## Files it creates

WIRE writes a few files during use:

- wire_run_TIMESTAMP.json — full archive of one run
- map_dots_v8.json — saved findings to reuse later
- findings_summary.log — only the strongest new findings
- wire_verify_TIMESTAMP.json — verification results
- wire_crash_TIMESTAMP.json — emergency dump if a run crashes

## Findings

WIRE stores short findings called dots.

Each dot is classified as:

- NEW_TERRITORY — a genuinely new finding
- PILLAR_ORBIT — too close to known attractor concepts
- OVERMAP — too similar to an existing finding

Only the strongest new findings are appended to findings_summary.log.

## Using prior findings

You can load prior findings from:

- a JSON file created by WIRE
- a Markdown compass file passed with --dots

This lets you continue building on earlier runs instead of starting from scratch every time.

## In simple terms

WIRE is a tool for:

- exploring a question with an AI
- tracking the route it took
- extracting reusable findings
- carrying those findings into future runs

It is less like a normal chatbot and more like a small reasoning workflow you can inspect and continue over time.
