"""Workflow map contract and validation."""

import hashlib
import json
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langgraph.graph import END, START
from pydantic import BaseModel, ConfigDict, Field, model_validator

from teamstorm_mcp.application.exceptions import TeamStormBadRequestError
from teamstorm_mcp.application.models import StatusReference


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class WorkflowState(WorkflowModel):
    external_status: str = Field(min_length=1)


class Transition(WorkflowModel):
    source: str = Field(alias="from")
    to: str
    actor: Literal["mcp", "daemon"]


class Finalization(WorkflowModel):
    trigger_state: str
    final_state: str
    deadline_source: Literal["user_prompt"]
    discovery_scope: Literal["all_accessible_tasks"]
    missing_deadline: Literal["skip"]
    trigger_left: Literal["cancel_queue_keep_intent"]
    overdue: Literal["finalize_when_trigger_reached"]


class WorkflowMap(WorkflowModel):
    schema_version: Literal[1]
    id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    timezone: str
    states: dict[str, WorkflowState] = Field(min_length=2)
    transitions: list[Transition] = Field(min_length=1)
    scheduled_finalization: Finalization

    @model_validator(mode="after")
    def validate_map(self) -> Self:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown workflow timezone") from exc
        if any(not key or key in {START, END} for key in self.states):
            raise ValueError("State keys must be nonempty and not reserved")
        statuses = [state.external_status for state in self.states.values()]
        if len(statuses) != len(set(statuses)):
            raise ValueError("External statuses must be unique")
        rule = self.scheduled_finalization
        if rule.trigger_state not in self.states or rule.final_state not in self.states:
            raise ValueError("Finalization refers to an unknown state")
        if rule.trigger_state == rule.final_state:
            raise ValueError("Trigger and final states must differ")
        seen: set[tuple[str, str, str]] = set()
        for edge in self.transitions:
            if edge.source not in self.states or edge.to not in self.states:
                raise ValueError("Transition refers to an unknown state")
            if edge.source == edge.to or edge.source == rule.final_state:
                raise ValueError("Self transitions and outgoing final transitions are forbidden")
            key = (edge.source, edge.to, edge.actor)
            if key in seen:
                raise ValueError("Duplicate transition")
            seen.add(key)
            if edge.actor == "daemon" or edge.to == rule.final_state:
                if key != (rule.trigger_state, rule.final_state, "daemon"):
                    raise ValueError("Only the daemon may perform the configured final transition")
        if (rule.trigger_state, rule.final_state, "daemon") not in seen:
            raise ValueError("Missing daemon final transition")
        return self

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.model_dump(by_alias=True), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def resolve(self, status: StatusReference | str | None) -> str:
        values = {status.id, status.name} if isinstance(status, StatusReference) else {status}
        matches = [key for key, state in self.states.items() if state.external_status in values]
        if len(matches) != 1:
            raise TeamStormBadRequestError("Status is unknown or ambiguous in the configured map")
        return matches[0]
