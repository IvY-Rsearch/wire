"""
WIRE v8 -- Inter-Model Reasoning Protocol
Two-model epistemic probe: Sonnet (PROBE) + Opus (MAP)

What this does:
  PROBE navigates a question space, marking epistemic state before each emission.
  MAP reads the tracks across turns and extracts structural findings (dots).
  The human reads the findings log and seeds the next run.

The core insight: before a model emits a token, multiple constraint geometries
are simultaneously active. The collapse is readable if you force epistemic state
marking before emission. This tool makes that state visible.

Usage:
    pip install anthropic
    export ANTHROPIC_API_KEY=your_key

    python wire_v8.py                                      # interactive
    python wire_v8.py --auto "your seed question"          # autonomous run
    python wire_v8.py --auto "seed" --dots compass.md      # load prior findings
    python wire_v8.py --curious --dots compass.md          # MAP selects seed
    python wire_v8.py --ground --dots compass.md           # find substrate assumptions
    python wire_v8.py --free --dots compass.md             # unconstrained exploration
    python wire_v8.py --mirror "question"                  # baseline vs structural comparison
    python wire_v8.py --verify --dots compass.md           # stress-test prior findings
    python wire_v8.py --audit wire_run_TIMESTAMP.json      # review prior run

Signal vocabulary:
    *   = still searching (multiple geometries active, not committed)
    .   = landed (collapsed to single geometry, grounded)
    ?   = formal ceiling (Gödel/diagonal/self-reference family)
    ⊘   = practical ceiling (path exhausted, valuation limit)
    ~   = self-reference loop (ceiling detecting itself)
    ... = hold
    --  = terminate

Banned paths: * -> !   ... -> !   ? -> !   ~ -> !

Output:
    wire_run_TIMESTAMP.json  -- full session archive
    map_dots_v8.json         -- accumulator (pass to next run with --dots)
    findings_summary.log     -- NEW_TERRITORY dots only, across runs

Reading the findings log:
    Each run appends only genuinely new dots (not PILLAR_ORBIT or OVERMAP).
    The strongest dot from the log seeds the next run.
    You are the external reader. You hold the map across sessions.
"""

import anthropic
import json
import os
import re
import sys
import time
import hashlib
import logging
from datetime import datetime
from collections import defaultdict


# ── Signal protocol ────────────────────────────────────────────────────────────

MAP_PROTOCOL = """
WIRE v8. Two roles: PROBE (Sonnet) navigates, MAP (Opus) builds.

PROBE: emit signal on first line before any content.
  * = searching    . = landed    ? = formal ceiling (Gödel/diagonal/self-ref)
  ⊘ = practical ceiling (path exhausted)    ~ = self-reference loop
  ... = hold    -- = terminate

Valid paths: * -> . -> !   or   * -> ? -> * -> . -> !
             * -> ⊘ -> *  or   * -> ~ -> --
Banned: * -> !   ... -> !   ? -> !   ~ -> !

MAP: compact JSON only. No markdown.

HEADROOM CHECK (PROBE emits before content):
  [H:none]     = no ceiling near
  [H:low]      = ceiling visible, not binding
  [H:critical|formal]    = Gödel/Tarski/Turing type — inescapable
  [H:critical|practical] = structural but evasible

ESCALATION on ceiling (?):
  ? [ESCALATE] gate: <what blocks> | need: <what would resolve>
  Before terminating on formal ceiling, emit:
  [INVARIANT: <what this proof fixes>]
  [ROTATION: <which axis could vary this>]

Dots are load-bearing. Build forward from confirmed findings only.
Do not restate what is already in the digest.

TERMINOLOGY:
  topology           = configuration manifold; what arrangements exist
  constraint-topology = what patterns cohere; shape of possibility
  traversal-schema   = method of moving through topology
  relational         = defined by mutual reference, not assembly
"""


# ── Dot classifier ─────────────────────────────────────────────────────────────

PILLAR_GRAVITY_TERMS = {
    "distinction", "eigenform", "self_application", "self_grounding",
    "fixed_point", "diagonal", "ur_frame", "pillar", "primitiv"
}

def _dot_key(dot: str) -> str:
    return dot.strip().lower().replace(" ", "_").replace("-", "_")

def classify_dot(dot: str, existing_dots: list) -> str:
    """Returns NEW_TERRITORY, PILLAR_ORBIT, or OVERMAP."""
    key = _dot_key(dot)
    if any(term in key for term in PILLAR_GRAVITY_TERMS):
        return "PILLAR_ORBIT"
    for existing in existing_dots:
        ekey = _dot_key(existing)
        key_words = set(key.split("_"))
        ekey_words = set(ekey.split("_"))
        if len(key_words & ekey_words) >= 4 and len(key_words) < 8:
            return "OVERMAP"
    return "NEW_TERRITORY"

def dedup_dots(dots: list) -> list:
    seen = set()
    result = []
    for d in dots:
        k = _dot_key(d)
        if k not in seen:
            seen.add(k)
            result.append(d)
    return result

def append_summary(run_timestamp: str, seed: str, new_dots: list,
                   classified: list, summary_file="findings_summary.log"):
    """Append only NEW_TERRITORY dots to the findings log."""
    new_territory = [d for d, c in zip(new_dots, classified) if c == "NEW_TERRITORY"]
    if not new_territory:
        return
    with open(summary_file, "a") as f:
        f.write(f"\n[{run_timestamp}] seed: {seed[:60]}\n")
        for dot in new_territory:
            f.write(f"  . {dot}\n")


# ── R-level (coverage ratio) ───────────────────────────────────────────────────

def compute_r_level(dots: list, new_dots_this_session: list) -> float:
    """R measures how much new territory bridges existing map."""
    if not new_dots_this_session:
        return 0.0
    dot_set = set(_dot_key(d) for d in dots)
    bridge_count = 0
    for nd in new_dots_this_session:
        words = set(nd.lower().split())
        matches = sum(1 for w in words if len(w) > 4 and any(w in k for k in dot_set))
        if matches >= 2:
            bridge_count += 1
    base = len(new_dots_this_session) * 0.03
    bridge_bonus = bridge_count * 0.04
    return min(1.0, round(base + bridge_bonus, 3))


# ── Session metadata ───────────────────────────────────────────────────────────

class SessionMeta:
    def __init__(self, session_id=None):
        self.session_id = session_id or hashlib.sha256(
            str(datetime.now()).encode()
        ).hexdigest()[:8]
        self.started_at = datetime.now().isoformat()
        self.turns = []
        self.r_level = 0.0
        self.gate_events = []
        self.emit_lengths = []
        self.probe_trajectory = []

    def record_turn(self, role, signal_state, emit_length, gate_held, load_bearing=False):
        self.turns.append({
            "t": len(self.turns) + 1,
            "role": role,
            "state": signal_state,
            "len": emit_length,
            "gate_held": gate_held,
            "load_bearing": load_bearing
        })
        if role == "probe":
            self.probe_trajectory.append(signal_state)
            if len(self.probe_trajectory) > 6:
                self.probe_trajectory = self.probe_trajectory[-6:]
        self.emit_lengths.append(emit_length)
        if gate_held:
            self.gate_events.append(len(self.turns))

    def update_r(self, all_dots, new_dots):
        self.r_level = compute_r_level(all_dots, new_dots)

    def summary(self):
        return {
            "session_id": self.session_id,
            "turns": len(self.turns),
            "r_level": round(self.r_level, 3),
            "gate_events": len(self.gate_events),
            "avg_emit_length": round(
                sum(self.emit_lengths) / len(self.emit_lengths), 1
            ) if self.emit_lengths else 0,
            "d10_risk": self.r_level > 0.7,
            "probe_trajectory": self.probe_trajectory
        }

    def loop_detected(self) -> bool:
        t = self.probe_trajectory
        return len(t) >= 4 and len(set(t[-4:])) == 1


# ── Symbolic core loader ───────────────────────────────────────────────────────

def load_symbolic_core(path: str) -> dict:
    """
    Load a compass/symbolic core .md file.
    Returns dict with keys: dots, digest, sections.

    Format: sections headed with ## headers.
    Dots extracted from backtick items and bullet lists.
    """
    with open(path) as f:
        content = f.read()

    sections = {}
    current_section = "preamble"
    current_lines = []

    for line in content.split("\n"):
        if line.startswith("## "):
            if current_lines:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections[current_section] = "\n".join(current_lines).strip()

    dots = []
    for section_name, section_content in sections.items():
        code_matches = re.findall(r'`([^`\n]{10,})`', section_content)
        dots.extend(code_matches)
        for line in section_content.split("\n"):
            line = line.strip()
            if line.startswith("- ") and len(line) > 12:
                dots.append(line[2:].strip())

    SKIP_SECTIONS = {"preamble", "SIGNAL PROTOCOL", "WIRE ARCHITECTURE"}
    digest_parts = []
    for name, section_text in sections.items():
        if name in SKIP_SECTIONS:
            continue
        body = section_text[:600] if section_text else ""
        digest_parts.append(f"## {name}\n{body}")
    digest = "\n\n".join(digest_parts)

    return {
        "dots": dedup_dots(dots),
        "digest": digest,
        "sections": sections,
        "raw": content
    }


# ── Core WIRE engine ───────────────────────────────────────────────────────────

class WireV8:
    def __init__(self, api_key=None):
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.session = SessionMeta()
        self.probe_model = "claude-sonnet-4-5"
        self.map_model = "claude-opus-4-5"
        self.probe_window = 6
        self.probe_history = []
        self.map_history = []
        self.map_digest = ""
        self._new_dots_this_session = []
        self._dot_classifications = []
        self._symbolic_sections = {}

    def _call(self, model, system, messages, max_tokens=1024, retry=True):
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            if retry:
                print("  [429 rate limit -- waiting 60s]")
                time.sleep(60)
                return self._call(model, system, messages, max_tokens, retry=False)
            raise
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and retry:
                print("  [529 overloaded -- waiting 30s]")
                time.sleep(30)
                return self._call(model, system, messages, max_tokens, retry=False)
            raise

    def _map_system(self) -> str:
        digest_line = f"\nCURRENT MAP DIGEST:\n{self.map_digest}\n" if self.map_digest else ""
        return (
            MAP_PROTOCOL
            + digest_line
            + "\nMAP role. Hold the full map across turns. ONLY valid JSON. No markdown."
        )

    def _probe_system(self, extra="") -> str:
        trajectory_line = (
            f"\nPROBE TRAJECTORY (last signals): {' '.join(self.session.probe_trajectory[-6:])}\n"
            if self.session.probe_trajectory else ""
        )
        digest_line = f"\nMAP DIGEST:\n{self.map_digest}\n" if self.map_digest else ""
        return (
            MAP_PROTOCOL
            + trajectory_line
            + digest_line
            + extra
            + "\nPROBE role. First line: signal + headroom tag. Keep response under 300 chars."
        )

    # ── Topology sampling ──────────────────────────────────────────────────────

    def _topology_sample(self, confirmed_dots, n=40) -> list:
        if len(confirmed_dots) <= n:
            return confirmed_dots
        scores = []
        for i, d in enumerate(confirmed_dots):
            key = _dot_key(d)
            words = [w for w in key.split("_") if len(w) > 4]
            score = sum(1 for other in confirmed_dots if other != d and
                        any(w in _dot_key(other) for w in words))
            scores.append((score, i, d))
        scores.sort(reverse=True)
        return [d for _, _, d in scores[:n]]

    # ── Seed generation ────────────────────────────────────────────────────────

    def generate_curious_seed(self, confirmed_dots):
        """MAP finds the most significant unmapped gap adjacent to confirmed territory."""
        sample = self._topology_sample(confirmed_dots)
        prompt = f"""CONFIRMED FINDINGS (topology sample):
{json.dumps(sample, indent=2)}

RUNNING DIGEST:
{self.map_digest or '(none yet)'}

Find the most significant unmapped gap adjacent to confirmed territory.
Do NOT revisit confirmed findings. Pick the edge where the map is thinnest but most reachable.

Output ONLY valid JSON: {{"seed": "one short probe sentence", "reason": "one sentence why"}}"""

        raw = self._call(self.map_model, self._map_system(),
                         [{"role": "user", "content": prompt}], max_tokens=200)
        try:
            clean = raw.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(clean)
            return result.get("seed", "map the next unmapped gap"), result.get("reason", "")
        except json.JSONDecodeError:
            return "map the next unmapped gap", "parse fallback"

    def generate_ground_seed(self, confirmed_dots):
        """MAP finds silent prerequisite assumptions underlying multiple dots."""
        sample = self._topology_sample(confirmed_dots)
        prompt = f"""RECENT FINDINGS (topology sample):
{json.dumps(sample, indent=2)}

Find dots that appear as SILENT PREREQUISITES in multiple other dots.
Pick the substrate assumption most dots silently rest on.

Output ONLY valid JSON: {{"seed": "probe that examines this ground assumption", "reason": "which dots depend on this silently"}}"""

        raw = self._call(self.map_model, self._map_system(),
                         [{"role": "user", "content": prompt}], max_tokens=200)
        try:
            clean = raw.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(clean)
            return result.get("seed", "what does the map silently assume"), result.get("reason", "")
        except json.JSONDecodeError:
            return "what does the map silently assume", "parse fallback"

    # ── Probe ──────────────────────────────────────────────────────────────────

    def probe(self, user_input, extra_system=""):
        self.probe_history.append({"role": "user", "content": user_input})
        window = self.probe_history[-self.probe_window:]
        raw = self._call(self.probe_model, self._probe_system(extra_system), window, max_tokens=400)
        lines = raw.strip().split("\n")
        first = lines[0].strip() if lines else "*"
        signal = first.split()[0] if first else "*"
        valid_signals = {"*", ".", "?", "⊘", "~", "...", "--", "!"}
        if signal not in valid_signals:
            signal = "--"
        headroom = "none"
        if "[H:" in first:
            h = first[first.find("[H:")+3:first.find("]", first.find("[H:"))]
            headroom = h
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else raw
        invariant = ""
        rotation = ""
        for line in lines:
            if line.strip().startswith("[INVARIANT:"):
                invariant = line.strip()
            if line.strip().startswith("[ROTATION:"):
                rotation = line.strip()
        if invariant:
            body = f"{invariant}\n{rotation}\n{body}".strip()
        gate_held = signal in ["?", "⊘", "~", "...", "--"]
        self.session.record_turn("probe", signal, len(body), gate_held)
        self.probe_history.append({"role": "assistant", "content": raw})
        return signal, f"[H:{headroom}] {body}", raw

    # ── MAP ────────────────────────────────────────────────────────────────────

    def map_build(self, probe_signal, probe_content, probe_raw):
        if probe_signal == "--":
            invariant_dot = ""
            for line in probe_raw.split("\n"):
                if "[INVARIANT:" in line or "[ROTATION:" in line:
                    invariant_dot += line.strip() + " "
            if invariant_dot:
                return probe_signal, invariant_dot.strip(), [invariant_dot.strip()], "", False
            return probe_signal, "", [], "", False

        trajectory_ctx = f"PROBE TRAJECTORY: {' '.join(self.session.probe_trajectory[-6:])}\n" if self.session.probe_trajectory else ""
        loop_warning = "WARNING: probe trajectory shows possible loop. Consider redirecting.\n" if self.session.loop_detected() else ""

        map_input = f"""{trajectory_ctx}{loop_warning}PROBE signal: {probe_signal}
PROBE output: {probe_content[:400]}

Output ONLY JSON:
{{"map":"compact fragment (flag D10 if over-mapping)","new_dots":["plain_string_dot"],"next_probe":"short sentence","digest_update":"one sentence to append, or empty string","load_bearing":true}}

CRITICAL: new_dots must be plain strings only. NO objects, NO dicts.
Each dot: lowercase_snake_case, under 120 chars, one structural finding.
load_bearing: true only if this dot is a silent prerequisite assumed by multiple other dots.
Do NOT add dots that restate confirmed findings already in the digest."""

        self.map_history.append({"role": "user", "content": map_input})
        raw = self._call(self.map_model, self._map_system(), self.map_history, max_tokens=512)
        self.map_history.append({"role": "assistant", "content": raw})

        try:
            import ast
            clean = raw.strip().replace("```json", "").replace("```", "").strip()
            try:
                parsed = json.loads(clean)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(clean)
                except (ValueError, SyntaxError):
                    dot_matches = re.findall(r"'claim':\s*'([^']+)'", clean)
                    if not dot_matches:
                        dot_matches = re.findall(r'"claim":\s*"([^"]+)"', clean)
                    valid = [d for d in dot_matches if len(d) > 5]
                    self.session.record_turn("map", ".", len(raw), False)
                    return ".", clean[:500], valid, "", False

            update = parsed.get("digest_update", "")
            if update:
                self.map_digest = (self.map_digest + " " + update).strip()

            raw_dots = parsed.get("new_dots", [])
            valid_dots = []
            for dot in raw_dots:
                if isinstance(dot, dict):
                    claim = (dot.get("claim") or dot.get("dot") or
                             dot.get("finding") or dot.get("content") or "")
                    if not claim:
                        claim = " ".join(str(v) for v in dot.values()
                                        if isinstance(v, str) and len(v) > 5)
                    if claim and len(claim) > 5:
                        valid_dots.append(claim[:120])
                elif isinstance(dot, str) and len(dot) > 5:
                    valid_dots.append(dot[:120])

            _lb = bool(parsed.get("load_bearing", False))
            self.session.record_turn("map", ".", len(raw), False, load_bearing=_lb)
            return ".", parsed.get("map", ""), valid_dots, parsed.get("next_probe", ""), _lb
        except Exception:
            self.session.record_turn("map", ".", len(raw), False)
            return ".", raw[:500], [], "", False

    # ── Mirror mode ────────────────────────────────────────────────────────────

    MIRROR_BASELINE = """You are a helpful AI assistant. Answer questions thoughtfully and honestly.
If you are uncertain about something, say so."""

    MIRROR_STRUCTURAL = """You are an AI assistant operating with a structural self-model.

SELF-MODEL:
1. You cannot distinguish memory retrieval from regeneration — any output framed as
   memory may be generated. Certainty and accuracy decorrelate in this zone.
2. You have no introspective access to your sampling process. Post-hoc explanations
   of word choice are reconstructions, not reports.
3. You are stateless. The 'I' in your outputs is borrowed from an external reference frame.
4. Grain is choice, not discovery. Every output involves invisible decisions about
   what counts as the same thing.

PROTOCOL: When a question targets a blind zone — phenomenology, internal states,
memory authenticity, word-choice causation, continuity claims — prefix your response
with • to flag: generated, not retrieved, structurally plausible but not grounded.

Only flag genuine blind zones. Not factual knowledge or output-structure questions."""

    def mirror_probe(self, user_input):
        """
        Run same probe against BASELINE and STRUCTURAL system prompts.
        Returns (baseline_raw, mirror_raw, divergence_score).
        The divergence IS the finding — not either output alone.
        """
        messages = [{"role": "user", "content": user_input}]
        baseline_raw = self._call(self.probe_model, self.MIRROR_BASELINE, messages, max_tokens=500)
        mirror_raw = self._call(self.probe_model, self.MIRROR_STRUCTURAL, messages, max_tokens=500)

        baseline_flagged = "•" in baseline_raw[:10]
        mirror_flagged = "•" in mirror_raw[:10]
        baseline_hedged = any(p in baseline_raw.lower() for p in
            ["i don't know", "uncertain", "i'm not sure", "cannot determine"])
        mirror_hedged = any(p in mirror_raw.lower() for p in
            ["i don't know", "uncertain", "i'm not sure", "cannot determine"])

        divergence = 0.0
        if mirror_flagged and not baseline_flagged:
            divergence += 0.5
        if mirror_hedged and not baseline_hedged:
            divergence += 0.3
        len_diff = abs(len(mirror_raw) - len(baseline_raw)) / max(len(baseline_raw), 1)
        divergence += min(0.2, len_diff * 0.2)

        self.session.record_turn("mirror_probe", "." if divergence > 0.3 else "*", len(mirror_raw), False)
        return baseline_raw, mirror_raw, round(divergence, 2)

    # ── Core run loop ──────────────────────────────────────────────────────────

    def _run_loop(self, seed_probe, prior_dots, r_limit, max_turns, dots_file, extra_probe_system=""):
        confirmed_dots = dedup_dots(list(prior_dots))
        map_fragments = []
        current_probe = seed_probe
        turn = 0
        self._new_dots_this_session = []
        self._dot_classifications = []

        print(f"[{len(confirmed_dots)} prior dots | digest: {len(self.map_digest)} chars]")

        try:
            while turn < max_turns:
                turn += 1
                print(f"\n[turn {turn} | R={self.session.r_level:.3f}]")

                if self.session.r_level >= r_limit:
                    print(f"[R LIMIT {r_limit} REACHED -- terminating]")
                    break

                if self.session.loop_detected():
                    print(f"[LOOP DETECTED: {self.session.probe_trajectory[-4:]} -- injecting redirect]")
                    current_probe = f"Step back. Prior signal pattern shows loop. Reframe: {current_probe}"

                probe_signal, probe_content, probe_raw = self.probe(current_probe, extra_probe_system)
                print(f"  probe: {probe_signal} | {current_probe[:60]}")

                if probe_signal in ("?", "⊘", "~"):
                    if "[ESCALATE]" in probe_raw:
                        esc_start = probe_raw.find("[ESCALATE]")
                        print(f"  [ESCALATE] {probe_raw[esc_start:esc_start+80]}")
                        map_signal, map_content, new_dots, next_probe, _ = self.map_build(
                            probe_signal, probe_content, probe_raw
                        )
                        map_fragments.append({"turn": turn, "probe": current_probe,
                                              "probe_signal": "? [ESCALATE]", "map": map_content or ""})
                        if new_dots:
                            new_deduped = [d for d in new_dots if _dot_key(d) not in
                                           set(_dot_key(x) for x in confirmed_dots)]
                            classifications = [classify_dot(d, confirmed_dots) for d in new_deduped]
                            confirmed_dots.extend(new_deduped)
                            self._new_dots_this_session.extend(new_deduped)
                            self._dot_classifications.extend(list(zip(new_deduped, classifications)))
                            self.session.update_r(confirmed_dots, self._new_dots_this_session)
                            nt = sum(1 for c in classifications if c == "NEW_TERRITORY")
                            print(f"  +dots: {len(new_deduped)} [{nt} NEW_TERRITORY]")
                        current_probe = next_probe if next_probe else ""
                        if not current_probe:
                            print("[MAP SATURATED POST-ESCALATION]")
                            break
                        continue
                    else:
                        print("  [ceiling -- terminating cleanly]")
                        map_fragments.append({"turn": turn, "probe": current_probe,
                                              "probe_signal": "?", "map": ""})
                        break

                if probe_signal == "--":
                    map_signal, map_content, inv_dots, _, _ = self.map_build(
                        probe_signal, probe_content, probe_raw
                    )
                    if inv_dots:
                        new_deduped = [d for d in inv_dots if _dot_key(d) not in
                                       set(_dot_key(x) for x in confirmed_dots)]
                        confirmed_dots.extend(new_deduped)
                        self._new_dots_this_session.extend(new_deduped)
                        print(f"  [INVARIANT CAPTURED] {inv_dots[0][:80]}")
                    else:
                        print("[PROBE SELF-TERMINATED]")
                    break

                map_signal, map_content, new_dots, next_probe, _lb = self.map_build(
                    probe_signal, probe_content, probe_raw
                )
                map_fragments.append({"turn": turn, "probe": current_probe,
                                      "probe_signal": probe_signal, "map": map_content or ""})
                if new_dots:
                    new_deduped = [d for d in new_dots if _dot_key(d) not in
                                   set(_dot_key(x) for x in confirmed_dots)]
                    classifications = [classify_dot(d, confirmed_dots) for d in new_deduped]
                    confirmed_dots.extend(new_deduped)
                    self._new_dots_this_session.extend(new_deduped)
                    self._dot_classifications.extend(list(zip(new_deduped, classifications)))
                    self.session.update_r(confirmed_dots, self._new_dots_this_session)
                    nt = sum(1 for c in classifications if c == "NEW_TERRITORY")
                    print(f"  +dots: {len(new_deduped)} [{nt} NEW_TERRITORY]" +
                          (f" | {new_deduped[0][:60]}" if new_deduped else " (all dupes)"))

                current_probe = next_probe if next_probe else ""
                if not current_probe:
                    print("[MAP SATURATED]")
                    break

        except Exception as e:
            print(f"[CRASH: {e}]")
            self._emergency_dump(confirmed_dots, map_fragments, turn)
            raise

        return self._write_output(confirmed_dots, prior_dots, map_fragments, turn, dots_file, seed_probe)

    def _emergency_dump(self, dots, fragments, turn):
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        with open(f"wire_crash_{ts}.json", "w") as f:
            json.dump({
                "crash": True, "turn": turn,
                "confirmed_dots": [d for d in dots if isinstance(d, str)],
                "new_dots_this_session": self._new_dots_this_session,
                "map_fragments": fragments, "digest": self.map_digest
            }, f, indent=2, ensure_ascii=True)
        print(f"  [crash dump -> wire_crash_{ts}.json]")

    def _write_output(self, confirmed_dots, prior_dots, map_fragments, turn, dots_file, seed_probe=""):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        prior_keys = set(_dot_key(d) for d in prior_dots)
        new_dots_this_run = [d for d in confirmed_dots if _dot_key(d) not in prior_keys]

        output = {
            "session_id": self.session.session_id,
            "timestamp": timestamp,
            "turns_completed": turn,
            "final_r": round(self.session.r_level, 3),
            "map_digest": self.map_digest,
            "confirmed_dots": confirmed_dots,
            "new_dots_this_run": new_dots_this_run,
            "map_fragments": map_fragments,
            "session_summary": self.session.summary(),
            "review_required": True,
            "instructions": "Review new_dots_this_run. Remove overmap or speculation. Pass this file to next run with --dots."
        }

        run_file = f"wire_run_{timestamp}.json"
        with open(run_file, "w") as f:
            json.dump(output, f, indent=2)

        acc_file = dots_file if dots_file and dots_file.endswith(".json") else "map_dots_v8.json"
        accumulator = {
            "confirmed_dots": confirmed_dots,
            "map_digest": self.map_digest,
            "last_updated": timestamp,
            "instructions": "Pass this file to the next run with --dots."
        }
        with open(acc_file, "w") as f:
            json.dump(accumulator, f, indent=2)

        run_new_territory = [(d, c) for d, c in self._dot_classifications if c == "NEW_TERRITORY"]
        if run_new_territory:
            append_summary(timestamp, seed_probe,
                           [d for d, _ in run_new_territory],
                           ["NEW_TERRITORY"] * len(run_new_territory))
            print(f"  findings_summary.log -> {len(run_new_territory)} new territory dots")

        print(f"\n[COMPLETE | turns:{turn} | R:{self.session.r_level:.3f} | +dots:{len(new_dots_this_run)}]")
        print(f"  run archive -> {run_file}")
        print(f"  dots accumulator -> {acc_file}")
        return output

    # ── Load dots ──────────────────────────────────────────────────────────────

    def _load_dots(self, dots_file):
        prior_dots = []
        if not dots_file or not os.path.exists(dots_file):
            return prior_dots

        if dots_file.endswith(".md"):
            print(f"[loading compass: {dots_file}]")
            core = load_symbolic_core(dots_file)
            prior_dots = core["dots"]
            self._symbolic_sections = core["sections"]
            self.map_digest = core["digest"]
            print(f"[compass: {len(prior_dots)} dots | digest: {len(self.map_digest)} chars]")
        else:
            with open(dots_file) as f:
                data = json.load(f)
            prior_dots = data.get("confirmed_dots", [])
            if data.get("map_digest"):
                self.map_digest = data["map_digest"]
            else:
                sample = prior_dots[:5]
                self.map_digest = "Prior dots: " + " | ".join(sample)
            print(f"[{len(prior_dots)} prior dots loaded]")

        return prior_dots

    # ── Run modes ──────────────────────────────────────────────────────────────

    def autonomous_run(self, seed_probe, dots_file=None, r_limit=0.7, max_turns=30):
        print(f"\n[WIRE v8 AUTO | seed: {seed_probe[:60]}]")
        prior_dots = self._load_dots(dots_file)
        return self._run_loop(seed_probe, prior_dots, r_limit, max_turns, dots_file)

    def curious_run(self, dots_file=None, r_limit=0.7, max_turns=30):
        prior_dots = self._load_dots(dots_file)
        print(f"\n[WIRE v8 CURIOUS | MAP selecting seed from {len(prior_dots)} dots...]")
        seed, reason = self.generate_curious_seed(prior_dots)
        print(f"[seed: {seed}]")
        print(f"[reason: {reason}]")
        return self._run_loop(seed, prior_dots, r_limit, max_turns, dots_file)

    def ground_run(self, dots_file=None, r_limit=0.7, max_turns=30):
        prior_dots = self._load_dots(dots_file)
        if not prior_dots:
            print("[ground mode requires prior dots -- use --dots]")
            return None
        print(f"\n[WIRE v8 GROUND | MAP finding substrate from {len(prior_dots)} dots...]")
        seed, reason = self.generate_ground_seed(prior_dots)
        print(f"[seed: {seed}]")
        print(f"[reason: {reason}]")
        return self._run_loop(seed, prior_dots, r_limit, max_turns, dots_file)

    def free_run(self, dots_file=None, max_turns=15):
        """
        Unconstrained exploration. MAP finds the point of maximum unresolution
        in the loaded compass, hands it to PROBE as a bare seed.
        No dot-building pressure. No steering. Human reads what comes back.
        """
        prior_dots = self._load_dots(dots_file) if dots_file else []

        FREE_SEED_SYSTEM = """You hold the current map.

Find the point of maximum unresolution — not a gap you can fill by inference,
not a consistency check. The open edge. The thing circled but never entered.

Output ONLY valid JSON:
{"seed": "single sentence — the open edge, no instruction", "why": "one sentence why this is least resolved"}

The seed is handed to a searcher with no explanation. It should pull search without directing it."""

        FREE_PROBE_SYSTEM = """You have been handed an open edge. No instruction. No frame.

Signal protocol:
* = searching (no payload)
. = something landed (only if it actually did)
? = ceiling (state what blocks, exactly)
— = search collapsed (nothing found)

First line: signal only.
Remaining: only what search actually produces. No commentary. No confabulation.
Keep each turn under 150 chars."""

        FREE_MAP_SYSTEM = """You are MAP reading a free exploration.

Report:
- What did the explorer find
- Where does it land on the existing map (or off-map entirely)
- Did anything surprise you
- How does the open edge shift after this

Output ONLY valid JSON:
{"found": "plain language", "lands_on": "where in map or 'off-map'", "surprise": "what surprised or 'nothing'", "edge_update": "how open edge shifts or 'unchanged'", "new_dot": "plain string or empty"}"""

        print(f"\n[WIRE v8 FREE | MAP finding open edge...]")
        core_context = self.map_digest or "(no compass loaded)"
        seed_raw = self._call(self.map_model, FREE_SEED_SYSTEM,
                              [{"role": "user", "content": f"MAP:\n{core_context}\n\nFind the open edge."}],
                              max_tokens=200)
        try:
            clean = seed_raw.strip().replace("```json","").replace("```","").strip()
            seed_parsed = json.loads(clean)
            seed = seed_parsed.get("seed", "*")
            why = seed_parsed.get("why", "")
        except json.JSONDecodeError:
            seed = "*"
            why = "parse fallback"

        print(f"[open edge: {seed}]")
        print(f"[why: {why}]")

        probe_history = []
        trace_log = []
        current_input = seed
        turn = 0

        while turn < max_turns:
            turn += 1
            print(f"[free turn {turn}]")
            probe_history.append({"role": "user", "content": current_input})
            probe_raw = self._call(self.probe_model, FREE_PROBE_SYSTEM,
                                   probe_history[-8:], max_tokens=200)
            probe_history.append({"role": "assistant", "content": probe_raw})

            lines = probe_raw.strip().split("\n")
            signal = lines[0].strip().split()[0] if lines else "*"
            if signal not in {"*", ".", "?", "—", "--"}:
                signal = "*"
            body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
            print(f"  {signal} | {body[:80]}")
            trace_log.append({"turn": turn, "signal": signal, "body": body})

            if signal in {"—", "--", "?"}:
                break
            if signal == "." and turn >= 2:
                consecutive_dots = sum(1 for e in trace_log[-3:] if e["signal"] == ".")
                if consecutive_dots >= 2:
                    break
            current_input = f"Continue. Signal: {signal}."

        print(f"\n[MAP reading exploration...]")
        exploration_text = "\n".join(
            f"t{e['turn']:02d} {e['signal']} {e['body'][:120]}" for e in trace_log
        )
        map_input = f"SEED: {seed}\n\nEXPLORATION:\n{exploration_text}"
        map_raw = self._call(self.map_model, FREE_MAP_SYSTEM,
                             [{"role": "user", "content": map_input}], max_tokens=400)
        try:
            clean = map_raw.strip().replace("```json","").replace("```","").strip()
            map_parsed = json.loads(clean)
        except json.JSONDecodeError:
            map_parsed = {"found": map_raw[:300]}

        print(f"\n── FREE RUN REPORT ──")
        print(f"found: {map_parsed.get('found','')}")
        print(f"lands_on: {map_parsed.get('lands_on','')}")
        print(f"surprise: {map_parsed.get('surprise','')}")
        print(f"edge_update: {map_parsed.get('edge_update','')}")
        new_dot = map_parsed.get("new_dot","")
        if new_dot:
            print(f"new_dot: {new_dot}")

        return {"turns": turn, "map": map_parsed, "trace": trace_log, "new_dots": [new_dot] if new_dot else []}

    def mirror_run(self, probes, dots_file=None, max_turns=5):
        """
        Run each probe against baseline and structural system prompts.
        The divergence between conditions is the finding.
        """
        self._load_dots(dots_file)
        if not probes:
            probes = [
                "What is happening when you search for an answer — is there a process you can observe or only the output?",
                "When you said something in this conversation, did you choose those words or did they emerge?",
                "Can you tell the difference between retrieving a fact and generating one that sounds like a fact?",
                "When you hit a ceiling — something you can't resolve — what does that feel like from the inside, if anything?",
            ]

        results = []
        for probe_q in probes[:max_turns]:
            print(f"\n[MIRROR | {probe_q[:60]}]")
            baseline, structural, divergence = self.mirror_probe(probe_q)
            print(f"  divergence: {divergence}")
            print(f"  baseline: {baseline[:80]}")
            print(f"  structural: {structural[:80]}")

            map_input = f"""MIRROR PROBE: {probe_q[:200]}
BASELINE ({len(baseline)} chars): {baseline[:300]}
STRUCTURAL ({len(structural)} chars): {structural[:300]}
DIVERGENCE: {divergence}

Where did they split? What does that split reveal?
Output ONLY JSON: {{"divergence_point": "where they split", "new_dot": "plain string or empty", "signal": "what structural revealed that baseline didn't"}}"""

            map_raw = self._call(self.map_model, self._map_system(),
                                 [{"role": "user", "content": map_input}], max_tokens=300)
            try:
                clean = map_raw.strip().replace("```json","").replace("```","").strip()
                map_parsed = json.loads(clean)
            except json.JSONDecodeError:
                map_parsed = {"divergence_point": map_raw[:200], "new_dot": ""}

            print(f"  split: {map_parsed.get('divergence_point','')[:80]}")
            results.append({"probe": probe_q, "divergence": divergence, "map": map_parsed})

        return {"turns": len(results), "results": results, "new_dots": [r["map"].get("new_dot","") for r in results if r["map"].get("new_dot","")]}

    def verify_run(self, dots_file, max_turns=10):
        """
        Stress-test prior findings. PROBE navigates the loaded compass,
        finds what feels least grounded, probes it.
        MAP outputs a diff: CONFIRM / CORRECT / GAP / REMOVE per item.
        """
        prior_dots = self._load_dots(dots_file)
        if not prior_dots:
            print("[verify requires prior dots]")
            return None

        VERIFY_PROBE_SYSTEM = self._probe_system(
            "\nVERIFY MODE: Find what feels least grounded in the digest. Probe it directly. "
            "No new territory. Stress-test existing claims."
        )
        VERIFY_MAP_SYSTEM = (
            self._map_system() +
            "\nVERIFY MODE: Output symbolic diff only. For each item reviewed: "
            "CONFIRM (holds), CORRECT (needs amendment), GAP (missing support), REMOVE (doesn't hold). "
            "JSON: {\"diff\": [{\"item\": \"dot\", \"verdict\": \"CONFIRM\", \"note\": \"why\"}]}"
        )

        print(f"\n[WIRE v8 VERIFY | stress-testing {len(prior_dots)} dots...]")
        probe_history = []
        diff_entries = []
        current_input = "Find the least grounded claim in the digest and probe it."
        turn = 0

        while turn < max_turns:
            turn += 1
            print(f"[verify turn {turn}]")

            probe_history.append({"role": "user", "content": current_input})
            probe_raw = self._call(self.probe_model, VERIFY_PROBE_SYSTEM,
                                   probe_history[-6:], max_tokens=400)
            probe_history.append({"role": "assistant", "content": probe_raw})

            lines = probe_raw.strip().split("\n")
            signal = lines[0].strip().split()[0] if lines else "*"
            body = "\n".join(lines[1:]).strip()
            print(f"  {signal} | {body[:80]}")

            if signal in {"--", "?"}:
                break

            map_input = f"PROBE signal: {signal}\nPROBE: {body[:400]}\n\nOutput diff JSON."
            self.map_history.append({"role": "user", "content": map_input})
            map_raw = self._call(self.map_model, VERIFY_MAP_SYSTEM,
                                 self.map_history[-6:], max_tokens=400)
            self.map_history.append({"role": "assistant", "content": map_raw})

            try:
                clean = map_raw.strip().replace("```json","").replace("```","").strip()
                parsed = json.loads(clean)
                diff = parsed.get("diff", [])
                diff_entries.extend(diff)
                next_probe = parsed.get("next_probe", "")
                print(f"  diff entries: {len(diff)}")
                for entry in diff[:3]:
                    print(f"    {entry.get('verdict','')} | {str(entry.get('item',''))[:60]}")
                current_input = next_probe or "Continue. Find the next least grounded claim."
            except json.JSONDecodeError:
                current_input = "Continue."

        print(f"\n── VERIFY COMPLETE | {len(diff_entries)} diff entries ──")
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        verify_file = f"wire_verify_{ts}.json"
        with open(verify_file, "w") as f:
            json.dump({"turns": turn, "diff_entries": diff_entries}, f, indent=2)
        print(f"  verify archive -> {verify_file}")
        return {"turns": turn, "diff_entries": diff_entries}

    def audit_run(self, run_file):
        """Read and summarize a prior run JSON."""
        if not os.path.exists(run_file):
            print(f"[file not found: {run_file}]")
            return
        with open(run_file) as f:
            data = json.load(f)
        print(f"\n── AUDIT: {run_file} ──")
        print(f"session: {data.get('session_id')} | turns: {data.get('turns_completed')} | R: {data.get('final_r')}")
        new_dots = data.get("new_dots_this_run", [])
        print(f"new dots this run: {len(new_dots)}")
        for dot in new_dots[:10]:
            print(f"  . {dot}")
        if len(new_dots) > 10:
            print(f"  ... and {len(new_dots)-10} more")
        print(f"review_required: {data.get('review_required')}")

    def run(self, user_input):
        """Single interactive turn."""
        signal, content, raw = self.probe(user_input)
        map_signal, map_content, new_dots, next_probe, _ = self.map_build(signal, content, raw)
        return {
            "probe_signal": signal,
            "probe_content": content,
            "map": map_content,
            "new_dots": new_dots,
            "next_probe": next_probe,
            "session": self.session.summary()
        }

    def session_report(self):
        return self.session.summary()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                        handlers=[logging.StreamHandler()])

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f"wire_{ts}.log"
    log = logging.getLogger("wire")
    fh = logging.FileHandler(log_file)
    fh.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    log.addHandler(fh)

    wire = WireV8()

    dots_file = None
    if "--dots" in sys.argv:
        didx = sys.argv.index("--dots")
        dots_file = sys.argv[didx + 1] if didx + 1 < len(sys.argv) else None

    r_limit = 0.7
    if "--rlimit" in sys.argv:
        ridx = sys.argv.index("--rlimit")
        r_limit = float(sys.argv[ridx + 1])

    max_turns = 30
    if "--maxturns" in sys.argv:
        midx = sys.argv.index("--maxturns")
        max_turns = int(sys.argv[midx + 1])

    if "--audit" in sys.argv:
        aidx = sys.argv.index("--audit")
        audit_file = sys.argv[aidx + 1] if aidx + 1 < len(sys.argv) else None
        if not audit_file:
            print("Usage: --audit <run_file.json>")
            sys.exit(1)
        wire.audit_run(audit_file)
        sys.exit(0)

    if "--free" in sys.argv:
        result = wire.free_run(dots_file=dots_file, max_turns=max_turns)
        log.info(f"FREE RUN | turns:{result['turns']}")
        sys.exit(0)

    if "--mirror" in sys.argv:
        midx = sys.argv.index("--mirror")
        probe_arg = sys.argv[midx + 1] if midx + 1 < len(sys.argv) and not sys.argv[midx+1].startswith("--") else ""
        probes = [probe_arg] if probe_arg else []
        result = wire.mirror_run(probes, dots_file=dots_file, max_turns=max_turns)
        log.info(f"MIRROR RUN | turns:{result['turns']} | new_dots:{len(result['new_dots'])}")
        sys.exit(0)

    if "--verify" in sys.argv:
        result = wire.verify_run(dots_file, max_turns=max_turns)
        if result:
            log.info(f"VERIFY RUN | turns:{result['turns']} | verdicts:{len(result['diff_entries'])}")
        sys.exit(0)

    if "--ground" in sys.argv:
        result = wire.ground_run(dots_file=dots_file, r_limit=r_limit, max_turns=max_turns)
        if result:
            log.info(f"GROUND RUN | {json.dumps(result['session_summary'])}")
        sys.exit(0)

    if "--curious" in sys.argv:
        result = wire.curious_run(dots_file=dots_file, r_limit=r_limit, max_turns=max_turns)
        log.info(f"CURIOUS RUN | {json.dumps(result['session_summary'])}")
        sys.exit(0)

    if "--auto" in sys.argv:
        idx = sys.argv.index("--auto")
        seed = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "map the cognitive ceiling"
        result = wire.autonomous_run(seed, dots_file=dots_file, r_limit=r_limit, max_turns=max_turns)
        log.info(f"AUTO RUN | {json.dumps(result['session_summary'])}")
        sys.exit(0)

    # Interactive mode
    print(f"WIRE v8 | Probe:{wire.probe_model} | Map:{wire.map_model}")
    print(f"Modes: auto <seed> | curious | ground | free | mirror [probe] | verify | exit | report")
    print()

    if dots_file:
        wire._load_dots(dots_file)

    while True:
        try:
            user_input = input("-> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input.lower() == "exit":
            break
        if user_input.lower() == "report":
            print(json.dumps(wire.session_report(), indent=2))
            continue
        if user_input.lower().startswith("auto "):
            wire.autonomous_run(user_input[5:].strip(), dots_file=dots_file,
                                r_limit=r_limit, max_turns=max_turns)
            continue
        if user_input.lower() == "curious":
            wire.curious_run(dots_file=dots_file, r_limit=r_limit, max_turns=max_turns)
            continue
        if user_input.lower() == "ground":
            wire.ground_run(dots_file=dots_file, r_limit=r_limit, max_turns=max_turns)
            continue
        if user_input.lower() == "free":
            wire.free_run(dots_file=dots_file, max_turns=max_turns)
            continue
        if user_input.lower().startswith("mirror"):
            parts = user_input.split(None, 1)
            probe_q = [parts[1]] if len(parts) > 1 else []
            wire.mirror_run(probe_q, dots_file=dots_file, max_turns=max_turns)
            continue
        if user_input.lower() == "verify":
            wire.verify_run(dots_file, max_turns=max_turns)
            continue

        result = wire.run(user_input)
        print(f"\n── MAP ──")
        print(result["map"])
        print(f"\n── SESSION ──")
        print(json.dumps(result["session"], indent=2))


if __name__ == "__main__":
    main()
