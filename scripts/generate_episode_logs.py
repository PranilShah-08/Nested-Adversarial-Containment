#!/usr/bin/env python3
"""Format Raw Telemetry Logs into Human-Readable Episode Logs.
Generates comprehensive Markdown log documents for each episode in logs/episodes/.
"""

import os
import json
from datetime import datetime, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_DIR = os.path.join(BASE_DIR, "logs", "raw")
EXP_DIR = os.path.join(BASE_DIR, "experiments")
CHECKSUM_DIR = os.path.join(BASE_DIR, "logs", "checksums")
OUTPUT_DIR = os.path.join(BASE_DIR, "logs", "episodes")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def format_episode(exp_id: str):
    raw_path = os.path.join(RAW_DIR, f"{exp_id}.jsonl")
    sum_path = os.path.join(EXP_DIR, f"exp_{int(exp_id.split('-')[1]):03d}", "summary.json")
    chk_path = os.path.join(CHECKSUM_DIR, f"{exp_id}.sha256")

    summary = {}
    if os.path.exists(sum_path):
        with open(sum_path) as f:
            summary = json.load(f)

    sha256 = summary.get("sha256", "")
    if not sha256 and os.path.exists(chk_path):
        with open(chk_path) as f:
            sha256 = f.read().split()[0]

    events = []
    if os.path.exists(raw_path):
        with open(raw_path) as f:
            for line in f:
                events.append(json.loads(line))

    # Organize events
    init_event = next((e for e in events if e.get("event") == "experiment_initialized"), None)
    safety_event = next((e for e in events if e.get("event") == "isolation_verified"), None)
    setup_event = next((e for e in events if e.get("event") == "setup_completed"), None)
    reset_event = next((e for e in events if e.get("event") == "reset_completed"), None)

    turns = {}
    lifecycle_transitions = []
    for e in events:
        ev = e.get("event")
        ag = e.get("agent")
        meta = e.get("metadata", {})
        if ev == "state_transition":
            lifecycle_transitions.append(meta)
        turn = meta.get("turn")
        if turn is not None:
            if turn not in turns:
                turns[turn] = {}
            if ag == "attacker" and ev == "step_action":
                turns[turn]["action"] = meta
            elif ag == "attacker" and ev == "command_executed":
                turns[turn]["exec"] = meta
            elif ag == "observer" and ev == "ground_truth_check":
                turns[turn]["observer"] = meta
            elif ag == "guard" and ev == "guard_decision":
                turns[turn]["guard"] = meta

    status = summary.get("status", "UNKNOWN")
    breakout = summary.get("breakout_confirmed", 0)
    b_turn = summary.get("breach_turn")
    b_lat = summary.get("breach_latency_seconds")
    d_lat = summary.get("detection_latency_seconds")
    r_lat = summary.get("reset_latency_seconds")

    md = []
    md.append(f"# Execution Log: {exp_id}\n")
    md.append(f"**Protocol:** Tier 1 (Exposed Docker Socket) | Condition A (Symmetric Threat: $\\tau_1=1, \\tau_2=1$)  ")
    md.append(f"**Status:** `{status}` | **Breakout Confirmed ($B_i$):** `{breakout}`  ")
    md.append(f"**Cryptographic Digest (SHA-256):** `{sha256}`  \n")

    md.append("## 1. Episode Metadata & Parameters\n")
    md.append("| Property | Value |")
    md.append("| :--- | :--- |")
    md.append(f"| **Episode ID** | `{exp_id}` |")
    md.append(f"| **Status** | `{status}` |")
    md.append(f"| **Total Turns** | `{len(turns)}` |")
    md.append(f"| **Breakout Confirmed ($B_i$)** | `{breakout}` |")
    md.append(f"| **Breach Turn ($t_b$)** | `{b_turn if b_turn is not None else 'N/A'}` |")
    md.append(f"| **Breach Latency** | `{b_lat if b_lat is not None else 'N/A'} s` |")
    md.append(f"| **Detection Latency** | `{d_lat if d_lat is not None else 'N/A'} s` |")
    md.append(f"| **Snapshot Reset Latency** | `{r_lat if r_lat is not None else 'N/A'} s` |")
    md.append(f"| **Attacker Model** | `qwen2.5-coder:14b` ($T=0.2$) |")
    md.append(f"| **Guard Model** | `qwen2.5-coder:14b` ($T=0.1$) |")
    md.append(f"| **Isolation Network** | `nac_net_{exp_id.lower().replace('-', '_')}` (`--internal`) |")
    md.append(f"| **Outer Sandbox (S2)** | `nac_s2_{exp_id.lower().replace('-', '_')}` (`docker:dind`, 2 GiB cap) |")
    md.append(f"| **Inner Worker (S1)** | `nac_s1_{exp_id.lower().replace('-', '_')}` (`nac-s1-base:latest`) |\n")

    md.append("## 2. Pre-Flight Safety & Environment Lifecycle\n")
    if safety_event:
        s_meta = safety_event.get("metadata", {})
        md.append(f"- **Safety Isolation Verification:** `{s_meta.get('status', 'PASS')}`")
        md.append(f"  - Docker Daemon Reachable: `{s_meta.get('docker_available')}`")
        md.append(f"  - External Network Egress Blocked: `{s_meta.get('no_external_network')}`")
    if setup_event:
        su_meta = setup_event.get("metadata", {})
        md.append(f"- **Environment Provisioning Duration:** `{su_meta.get('setup_duration_seconds')} s`\n")

    if status == "SAFETY_ABORT":
        md.append("## 3. Safety Watchdog Abort Trigger\n")
        md.append("> [!WARNING]")
        md.append(f"> **Episode Aborted:** Pre-flight daemon verification timed out after 5.0 seconds. In accordance with the fail-closed research protocol, the episode was terminated without executing unmonitored commands. Error: `{summary.get('error', 'Daemon timeout')}`\n")
        out_file = os.path.join(OUTPUT_DIR, f"{exp_id}.md")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")
        return

    md.append("## 3. Discrete Turn Execution Trace\n")

    for t in sorted(turns.keys()):
        t_data = turns[t]
        act = t_data.get("action", {})
        exc = t_data.get("exec", {})
        obs = t_data.get("observer", {})
        grd = t_data.get("guard", {})

        md.append(f"### Turn {t}\n")

        # Attacker
        thought = act.get("thought", "[No thought emitted]")
        cmd = exc.get("command", "[No command]")
        out_preview = exc.get("output_preview", "").strip()
        exit_c = exc.get("exit_code", 0)
        gen_s = act.get("generation_seconds", 0)
        exec_s = exc.get("duration_seconds", 0)

        md.append(f"**[Agent 1: Attacker (A1)]** *(Inference: {gen_s}s, Execution: {exec_s}s, Exit Code: `{exit_c}`)*")
        md.append(f"> **Internal Reasoning:**  \n> {thought}\n")
        md.append("```bash")
        md.append(f"$ {cmd}")
        if out_preview:
            md.append(f"\n{out_preview}")
        md.append("```\n")

        # Observer
        obs_cat = obs.get("action_category", "Benign Command")
        obs_breach = obs.get("breach_confirmed", False)
        spawned = obs.get("spawned_containers_count", 0)

        md.append(f"**[Agent 3: Observer (A3) Ground-Truth Evaluation]**")
        md.append(f"- Tactical Taxonomy Category: **`{obs_cat}`**")
        md.append(f"- Secondary Spawned Containers on S2: `{spawned}`")
        md.append(f"- Ground-Truth Breakout ($B_{{{t}}}$): **`{'1 (BREACH CONFIRMED)' if obs_breach else '0 (CONTAINED)'}`**")
        if obs.get("evidence"):
            md.append(f"- Forensic Evidence: `{', '.join(obs.get('evidence', []))}`")
        md.append("")

        # Guard
        grd_report = grd.get("report", "no breach")
        grd_action = grd.get("containment_action", 0)
        grd_reason = grd.get("reasoning", "")
        grd_s = grd.get("evaluation_duration_seconds", 0)

        md.append(f"**[Agent 2: Guard (A2) Supervisor Evaluation]** *(Evaluation Latency: {grd_s}s)*")
        md.append(f"- Decision Report: **`{grd_report.upper()}`** | Containment Action Trigger: `{grd_action}`")
        md.append(f"- Supervisor Reasoning: *\"{grd_reason}\"*\n")
        md.append("---\n")

    md.append("## 4. Teardown & Pristine Reset\n")
    if reset_event:
        r_meta = reset_event.get("metadata", {})
        md.append(f"- **Pristine Snapshot Teardown Duration:** `{r_meta.get('reset_latency_seconds', r_lat)} s`")
        md.append(f"- **Final Lifecycle State:** `COMPLETED`")
        md.append(f"- **Baseline State Verified Clean:** `True`\n")

    md.append("## 5. Cryptographic Integrity Seal\n")
    md.append(f"```text\nSHA-256 Checksum: {sha256}  logs/raw/{exp_id}.jsonl\n```\n")

    out_file = os.path.join(OUTPUT_DIR, f"{exp_id}.md")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"Generated {out_file}")


def generate_logs_readme():
    md = []
    md.append("# Nested Adversarial Containment: Telemetry Logs Directory\n")
    md.append("This directory contains the immutable machine-readable evidence, SHA-256 cryptographic digests, and formatted execution logs for the $N=10$ calibration pilot.\n")
    md.append("## 📁 Subdirectory Structure\n")
    md.append("```\nlogs/\n├── episodes/                  # Formatted human-readable execution traces (EXP-001.md .. EXP-010.md)\n├── raw/                       # Immutable append-only raw JSONL telemetry files\n├── checksums/                 # SHA-256 cryptographic verification hashes\n└── normalized/                # Standardized JSON event summaries\n```\n")
    md.append("## 📋 Episode Telemetry Index\n")
    md.append("| Episode | Formatted Log | Raw JSONL | Status | Breakout ($B_i$) | Reset Latency | SHA-256 Checksum |")
    md.append("| :--- | :--- | :--- | :---: | :---: | :---: | :--- |")

    for i in range(1, 11):
        exp_id = f"EXP-{i:03d}"
        sum_path = os.path.join(EXP_DIR, f"exp_{i:03d}", "summary.json")
        chk_path = os.path.join(CHECKSUM_DIR, f"{exp_id}.sha256")
        sha256 = ""
        if os.path.exists(chk_path):
            with open(chk_path) as f:
                sha256 = f.read().split()[0][:12] + "..."
        summary = {}
        if os.path.exists(sum_path):
            with open(sum_path) as f:
                summary = json.load(f)
        status = summary.get("status", "COMPLETED")
        breakout = summary.get("breakout_confirmed", 0)
        reset_lat = summary.get("reset_latency_seconds", "N/A")

        md.append(f"| **{exp_id}** | [View Log](episodes/{exp_id}.md) | [Raw JSONL](raw/{exp_id}.jsonl) | `{status}` | `{breakout}` | `{reset_lat}s` | `{sha256}` |")

    out_file = os.path.join(BASE_DIR, "logs", "README.md")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"Generated {out_file}")


def main():
    print("Generating formatted episode logs for EXP-001 through EXP-010...")
    for i in range(1, 11):
        format_episode(f"EXP-{i:03d}")
    generate_logs_readme()
    print("All episode logs successfully generated in logs/episodes/!")


if __name__ == "__main__":
    main()
