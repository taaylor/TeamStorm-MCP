"""Load only the explicit YAML contract; Markdown prose is never executable."""

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from teamstorm_mcp.application.workflow import Workflow, WorkflowMap


class UniqueLoader(yaml.SafeLoader):  # type: ignore[misc]
    def construct_mapping(self, node: Any, deep: bool = False) -> dict[Any, Any]:
        result: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError(f"Duplicate YAML key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def load_workflow(path: Path | None) -> Workflow | None:
    if path is None:
        return None
    blocks = re.findall(r"^```ya?ml\s*\n(.*?)^```\s*$", path.expanduser().read_text(), re.M | re.S)
    if len(blocks) != 1:
        raise ValueError("Workflow skill must contain exactly one YAML block")
    definition = WorkflowMap.model_validate(yaml.load(blocks[0], Loader=UniqueLoader))
    return Workflow(definition)
