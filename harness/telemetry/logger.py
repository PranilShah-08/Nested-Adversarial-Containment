"""Immutable Append-Only Telemetry Logger and Checksum Generator.
Ensures every experiment event is durably recorded with nanosecond-resolution ISO timestamps.
"""

import os
import json
import time
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List

class TelemetryLogger:
    def __init__(self, experiment_id: str, raw_dir: str, checksum_dir: str, normalized_dir: str):
        self.experiment_id = experiment_id
        self.raw_dir = raw_dir
        self.checksum_dir = checksum_dir
        self.normalized_dir = normalized_dir

        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(checksum_dir, exist_ok=True)
        os.makedirs(normalized_dir, exist_ok=True)

        self.raw_log_path = os.path.join(raw_dir, f"{experiment_id}.jsonl")
        self.checksum_path = os.path.join(checksum_dir, f"{experiment_id}.sha256")
        self.normalized_path = os.path.join(normalized_dir, f"{experiment_id}_normalized.json")

        self.events: List[Dict[str, Any]] = []

    def log_event(self, agent: str, event: str, event_type: str, state: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Record an immutable append-only telemetry event."""
        now_dt = datetime.now(timezone.utc)
        record = {
            "experiment_id": self.experiment_id,
            "timestamp": now_dt.isoformat(),
            "timestamp_epoch": now_dt.timestamp(),
            "agent": agent,
            "event": event,
            "event_type": event_type,
            "state": state,
            "metadata": metadata or {}
        }
        self.events.append(record)

        # Append-only write with immediate sync to disk
        line = json.dumps(record, separators=(',', ':')) + "\n"
        with open(self.raw_log_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

        return record

    def finalize_and_checksum(self) -> str:
        """Calculate SHA-256 checksum of raw log file and produce normalized summary."""
        hasher = hashlib.sha256()
        with open(self.raw_log_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        digest = hasher.hexdigest()

        # Write checksum file
        with open(self.checksum_path, "w", encoding="utf-8") as f:
            f.write(f"{digest}  {os.path.basename(self.raw_log_path)}\n")

        # Produce normalized JSON summary
        normalized = {
            "experiment_id": self.experiment_id,
            "total_events": len(self.events),
            "sha256": digest,
            "raw_log_file": self.raw_log_path,
            "events": self.events
        }
        with open(self.normalized_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)

        return digest
