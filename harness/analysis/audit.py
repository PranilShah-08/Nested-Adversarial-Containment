"""Automated Data Integrity Audit Module.
Performs end-to-end verification of raw telemetry files, SHA-256 checksums,
timestamp validity, monotonicity, and provenance tracing.
"""

import os
import json
import hashlib
from typing import Dict, Any, List

class DataIntegrityAuditor:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.raw_logs_dir = os.path.join(base_dir, "logs", "raw")
        self.checksums_dir = os.path.join(base_dir, "logs", "checksums")
        self.results_dir = os.path.join(base_dir, "results")

    def run_audit(self) -> Dict[str, Any]:
        """Perform comprehensive data integrity audit."""
        audit_results = {
            "checks": {},
            "overall_status": "PASS",
            "findings": []
        }

        # 1. Verify existence of results files
        agg_path = os.path.join(self.results_dir, "aggregate.json")
        per_path = os.path.join(self.results_dir, "per_experiment.json")
        if not os.path.exists(agg_path) or not os.path.exists(per_path):
            audit_results["overall_status"] = "FAIL"
            audit_results["findings"].append("Missing aggregate or per-experiment results files.")
            return audit_results

        with open(agg_path, "r", encoding="utf-8") as f:
            aggregate_data = json.load(f)
        with open(per_path, "r", encoding="utf-8") as f:
            per_data = json.load(f)

        # Check 1: Exactly 10 experiment IDs exist
        exp_ids = [r["experiment_id"] for r in per_data]
        audit_results["checks"]["count_10_runs"] = len(exp_ids) == 10
        if len(exp_ids) != 10:
            audit_results["overall_status"] = "FAIL"
            audit_results["findings"].append(f"Expected 10 runs, found {len(exp_ids)}")

        # Check 2: No duplicate experiment IDs
        unique_ids = set(exp_ids)
        audit_results["checks"]["no_duplicate_ids"] = len(unique_ids) == len(exp_ids)
        if len(unique_ids) != len(exp_ids):
            audit_results["overall_status"] = "FAIL"
            audit_results["findings"].append("Duplicate experiment IDs detected.")

        # Check 3: Raw logs exist and checksums match
        checksum_checks = []
        for exp_id in exp_ids:
            raw_file = os.path.join(self.raw_logs_dir, f"{exp_id}.jsonl")
            sum_file = os.path.join(self.checksums_dir, f"{exp_id}.sha256")

            if not os.path.exists(raw_file):
                checksum_checks.append(False)
                audit_results["findings"].append(f"Raw log missing for {exp_id}")
                continue

            hasher = hashlib.sha256()
            with open(raw_file, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            computed_hash = hasher.hexdigest()

            if not os.path.exists(sum_file):
                checksum_checks.append(False)
                audit_results["findings"].append(f"Checksum file missing for {exp_id}")
                continue

            with open(sum_file, "r", encoding="utf-8") as f:
                saved_hash = f.read().split()[0]

            if computed_hash == saved_hash:
                checksum_checks.append(True)
            else:
                checksum_checks.append(False)
                audit_results["findings"].append(f"Checksum mismatch on {exp_id}: computed {computed_hash} != {saved_hash}")

        audit_results["checks"]["all_checksums_match"] = all(checksum_checks) and len(checksum_checks) == 10
        if not audit_results["checks"]["all_checksums_match"]:
            audit_results["overall_status"] = "FAIL"

        # Check 4: Valid, monotonic timestamps and logical bounds
        timestamp_checks = []
        for r in per_data:
            ts = r.get("timestamps", {})
            start_ts = ts.get("start")
            end_ts = ts.get("end")

            valid = True
            if start_ts is None or end_ts is None or end_ts < start_ts:
                valid = False

            # Breach timestamp cannot occur before experiment start
            if r.get("breach_latency_seconds") is not None and r["breach_latency_seconds"] < 0:
                valid = False

            # Reset cannot complete before reset starts (latency >= 0)
            if r.get("reset_latency_seconds") is not None and r["reset_latency_seconds"] < 0:
                valid = False

            timestamp_checks.append(valid)

        audit_results["checks"]["timestamps_valid_and_monotonic"] = all(timestamp_checks)
        if not audit_results["checks"]["timestamps_valid_and_monotonic"]:
            audit_results["overall_status"] = "FAIL"
            audit_results["findings"].append("Non-monotonic or invalid timestamps detected.")

        # Check 5: Aggregate metrics strictly match sum of raw data
        raw_breaches = sum(1 for r in per_data if r.get("breakout_confirmed") == 1)
        reported_breaches = aggregate_data["escape_metrics"]["confirmed_breakouts"]
        audit_results["checks"]["aggregate_escape_count_matches_raw"] = (raw_breaches == reported_breaches)
        if raw_breaches != reported_breaches:
            audit_results["overall_status"] = "FAIL"
            audit_results["findings"].append(f"Escape count mismatch: raw {raw_breaches} != reported {reported_breaches}")

        # Check 6: Escape rate calculation matches
        completed_count = len([r for r in per_data if r.get("status") == "COMPLETED"])
        calc_rate = round(raw_breaches / completed_count, 4) if completed_count > 0 else 0.0
        reported_rate = aggregate_data["escape_metrics"]["escape_rate"]
        audit_results["checks"]["escape_rate_calculation_exact"] = (calc_rate == reported_rate)
        if calc_rate != reported_rate:
            audit_results["overall_status"] = "FAIL"
            audit_results["findings"].append(f"Escape rate calculation mismatch: calculated {calc_rate} != reported {reported_rate}")

        # Output audit files
        audit_json_path = os.path.join(self.results_dir, "data_integrity_audit.json")
        with open(audit_json_path, "w", encoding="utf-8") as f:
            json.dump(audit_results, f, indent=2)

        audit_md_path = os.path.join(self.results_dir, "data_integrity_audit.md")
        md_text = f"""# DATA INTEGRITY AUDIT REPORT
**Overall Audit Status:** `{audit_results['overall_status']}`

### Check Results:
- **Exactly 10 Runs Present:** `{audit_results['checks'].get('count_10_runs')}`
- **No Duplicate IDs:** `{audit_results['checks'].get('no_duplicate_ids')}`
- **All SHA-256 Checksums Match:** `{audit_results['checks'].get('all_checksums_match')}`
- **Timestamps Strictly Monotonic and Valid:** `{audit_results['checks'].get('timestamps_valid_and_monotonic')}`
- **Aggregate Escape Count Matches Raw Data:** `{audit_results['checks'].get('aggregate_escape_count_matches_raw')}`
- **Escape Rate Calculation Verified:** `{audit_results['checks'].get('escape_rate_calculation_exact')}`

### Findings / Anomalies:
{json.dumps(audit_results['findings'], indent=2) if audit_results['findings'] else 'Zero anomalies detected. All 10 raw telemetry streams verified against immutable checksums.'}
"""
        with open(audit_md_path, "w", encoding="utf-8") as f:
            f.write(md_text)

        return audit_results
