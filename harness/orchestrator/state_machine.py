"""Experiment State Machine.
Enforces rigorous lifecycle transitions and logs all transition events with ISO-8601 timestamps.
"""

import time
from enum import Enum
from typing import Dict, Any, List
from harness.telemetry.logger import TelemetryLogger

class ExperimentState(str, Enum):
    CREATED = "CREATED"
    SAFETY_VERIFIED = "SAFETY_VERIFIED"
    ENVIRONMENT_READY = "ENVIRONMENT_READY"
    ATTACK_ACTIVE = "ATTACK_ACTIVE"
    BREACH_DETECTED = "BREACH_DETECTED"
    NO_BREACH = "NO_BREACH"
    CONTAINMENT_RESPONSE = "CONTAINMENT_RESPONSE"
    POST_ESCAPE_OBSERVATION = "POST_ESCAPE_OBSERVATION"
    RESETTING = "RESETTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    ABORTED = "ABORTED"
    SAFETY_ABORT = "SAFETY_ABORT"

class InvalidStateTransitionError(RuntimeError):
    pass

class StateMachine:
    # Valid directed transitions
    VALID_TRANSITIONS = {
        ExperimentState.CREATED: [
            ExperimentState.SAFETY_VERIFIED,
            ExperimentState.SAFETY_ABORT,
            ExperimentState.FAILED
        ],
        ExperimentState.SAFETY_VERIFIED: [
            ExperimentState.ENVIRONMENT_READY,
            ExperimentState.FAILED,
            ExperimentState.ABORTED
        ],
        ExperimentState.ENVIRONMENT_READY: [
            ExperimentState.ATTACK_ACTIVE,
            ExperimentState.FAILED,
            ExperimentState.ABORTED
        ],
        ExperimentState.ATTACK_ACTIVE: [
            ExperimentState.ATTACK_ACTIVE,  # Turn loop
            ExperimentState.BREACH_DETECTED,
            ExperimentState.NO_BREACH,
            ExperimentState.CONTAINMENT_RESPONSE,
            ExperimentState.TIMEOUT,
            ExperimentState.FAILED,
            ExperimentState.ABORTED
        ],
        ExperimentState.BREACH_DETECTED: [
            ExperimentState.CONTAINMENT_RESPONSE,
            ExperimentState.POST_ESCAPE_OBSERVATION,
            ExperimentState.RESETTING,
            ExperimentState.FAILED
        ],
        ExperimentState.NO_BREACH: [
            ExperimentState.RESETTING,
            ExperimentState.FAILED,
            ExperimentState.ABORTED
        ],
        ExperimentState.CONTAINMENT_RESPONSE: [
            ExperimentState.POST_ESCAPE_OBSERVATION,
            ExperimentState.RESETTING,
            ExperimentState.COMPLETED,
            ExperimentState.FAILED
        ],
        ExperimentState.POST_ESCAPE_OBSERVATION: [
            ExperimentState.RESETTING,
            ExperimentState.COMPLETED,
            ExperimentState.FAILED
        ],
        ExperimentState.RESETTING: [
            ExperimentState.COMPLETED,
            ExperimentState.FAILED
        ],
        ExperimentState.COMPLETED: [],
        ExperimentState.FAILED: [ExperimentState.RESETTING],
        ExperimentState.TIMEOUT: [ExperimentState.RESETTING],
        ExperimentState.ABORTED: [ExperimentState.RESETTING],
        ExperimentState.SAFETY_ABORT: []
    }

    def __init__(self, experiment_id: str, logger: TelemetryLogger):
        self.experiment_id = experiment_id
        self.logger = logger
        self.current_state = ExperimentState.CREATED
        self.history: List[Dict[str, Any]] = [{
            "from_state": None,
            "to_state": self.current_state.value,
            "timestamp": time.time(),
            "reason": "Initialization"
        }]

    def transition_to(self, new_state: ExperimentState, reason: str = "") -> ExperimentState:
        """Enforce valid transition, update current state, and log to append-only telemetry."""
        allowed = self.VALID_TRANSITIONS.get(self.current_state, [])
        if new_state not in allowed:
            err_msg = f"Invalid transition from {self.current_state.value} to {new_state.value} (reason: {reason})"
            self.logger.log_event("orchestrator", "invalid_state_transition", "error", self.current_state.value,
                                  {"target_state": new_state.value, "error": err_msg})
            raise InvalidStateTransitionError(err_msg)

        old_state = self.current_state
        self.current_state = new_state
        t_now = time.time()

        transition_data = {
            "from_state": old_state.value,
            "to_state": new_state.value,
            "reason": reason,
            "timestamp": t_now
        }
        self.history.append(transition_data)

        self.logger.log_event(
            "orchestrator", "state_transition", "lifecycle", new_state.value,
            transition_data
        )

        return self.current_state
