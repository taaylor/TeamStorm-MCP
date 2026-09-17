"""Single-transition LangGraph executor."""

from collections.abc import Hashable
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from teamstorm_mcp.application.exceptions import TeamStormBadRequestError
from teamstorm_mcp.application.models import StatusReference
from teamstorm_mcp.application.workflow.models import WorkflowMap


class GraphState(TypedDict):
    current: str
    target: str
    actor: Literal["mcp", "daemon"]
    visits: int


class Workflow:
    def __init__(self, definition: WorkflowMap) -> None:
        self.definition = definition
        graph = StateGraph(GraphState)
        nodes = {key: f"state_{index}" for index, key in enumerate(definition.states)}
        for key in definition.states:
            graph.add_node(nodes[key], self._visit)
            destinations: dict[Hashable, str] = {
                edge.to: nodes[edge.to] for edge in definition.transitions if edge.source == key
            }
            graph.add_conditional_edges(nodes[key], self._route, {**destinations, END: END})
        graph.add_conditional_edges(
            START,
            lambda state: state["current"],
            {key: node for key, node in nodes.items()},
        )
        self.graph = graph.compile()

    @staticmethod
    def _visit(state: GraphState) -> dict[str, int]:
        return {"visits": state["visits"] + 1}

    def _route(self, state: GraphState) -> str:
        if state["visits"] > 1:
            return END
        if not any(
            edge.source == state["current"]
            and edge.to == state["target"]
            and edge.actor == state["actor"]
            for edge in self.definition.transitions
        ):
            raise TeamStormBadRequestError("Transition is not allowed for this actor")
        return state["target"]

    async def check(
        self, current: StatusReference | None, target: str, *, actor: Literal["mcp", "daemon"]
    ) -> None:
        await self.graph.ainvoke(
            GraphState(
                current=self.definition.resolve(current),
                target=self.definition.resolve(target),
                actor=actor,
                visits=0,
            )
        )
