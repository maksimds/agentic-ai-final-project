"""PantryPal orchestrator: one entry point that coordinates all four agents.

Each user turn goes through three stages, one per design pattern:

1. Routing. The Kitchen Coordinator gets the message and either answers it
   (clarifying question / out of scope) or hands off to the Pantry Keeper or
   the Recipe Planner. The LLM picks the route; the orchestrator reads which
   agent finished the run (`result.last_agent`) to know where it went.

2. Human in the loop. Every run goes through `run_with_approvals`, so an
   update_pantry call pauses for the user's yes/no even after a handoff.

3. Evaluator-optimizer. If the Recipe Planner produced the answer, the
   orchestrator (code, not a prompt) sends the plan to the Pantry Verifier.
   On a fail, the verifier's issues go back to the planner for a revision.
   At most MAX_REVISIONS revisions, as the proposal specifies.

Every turn starts at the Coordinator again, so a follow-up about recipes after
a pantry question is routed fresh.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agents import Agent, Runner

from .kitchen_coordinator import build_kitchen_coordinator
from .pantry_keeper import build_pantry_keeper
from .pantry_verifier import Verdict, build_pantry_verifier
from .recipe_planner import RecipePlan, build_recipe_planner
from .runner import ask_in_terminal, run_with_approvals

MAX_REVISIONS = 2  # "It can do this twice" (proposal, evaluator-optimizer)

ROUTE_COORDINATOR = "coordinator"
ROUTE_PANTRY = "pantry"
ROUTE_RECIPE = "recipe"


@dataclass
class Attempt:
    plan: RecipePlan
    verdict: Verdict | None  # None when the planner found no recipe to verify


@dataclass
class TurnResult:
    reply: str
    route: str
    attempts: list[Attempt] = field(default_factory=list)  # recipe route only


class PantryPal:
    """Holds the four agents and the conversation history for one session."""

    def __init__(self, model, approve: Callable[[str, dict], bool] = ask_in_terminal):
        self.pantry_keeper = build_pantry_keeper(model)
        self.recipe_planner = build_recipe_planner(model)
        self.verifier = build_pantry_verifier(model)
        self.coordinator = build_kitchen_coordinator(
            model, self.pantry_keeper, self.recipe_planner)
        self.approve = approve
        self.history: list = []

    async def handle(self, user_message: str) -> TurnResult:
        user_item = {"role": "user", "content": user_message}
        result = await run_with_approvals(self.coordinator, self.history + [user_item], self.approve)

        route = self._route_of(result.last_agent)
        if route != ROUTE_RECIPE:
            self.history = result.to_input_list()
            return TurnResult(reply=str(result.final_output), route=route)

        attempts = await self._verify_loop(user_message, result.final_output_as(RecipePlan))
        reply = format_recipe_reply(attempts)
        # Keep only the final, user-facing answer in the shared history, not the
        # intermediate drafts and verdicts.
        self.history = self.history + [user_item, {"role": "assistant", "content": reply}]
        return TurnResult(reply=reply, route=route, attempts=attempts)

    def _route_of(self, agent: Agent) -> str:
        if agent is self.pantry_keeper:
            return ROUTE_PANTRY
        if agent is self.recipe_planner:
            return ROUTE_RECIPE
        return ROUTE_COORDINATOR

    async def _verify_loop(self, request: str, plan: RecipePlan) -> list[Attempt]:
        attempts: list[Attempt] = []
        for revision in range(MAX_REVISIONS + 1):
            if not plan.recipe_name:
                attempts.append(Attempt(plan, None))  # nothing to verify
                break

            verdict = await self._verify(request, plan)
            attempts.append(Attempt(plan, verdict))
            if verdict.passed or revision == MAX_REVISIONS:
                break
            plan = await self._revise(request, plan, verdict)
        return attempts

    async def _verify(self, request: str, plan: RecipePlan) -> Verdict:
        prompt = (f"User request: {request}\n\n"
                  f"Proposed recipe (JSON):\n{plan.model_dump_json(indent=2)}")
        result = await Runner.run(self.verifier, prompt)
        return result.final_output_as(Verdict)

    async def _revise(self, request: str, plan: RecipePlan, verdict: Verdict) -> RecipePlan:
        prompt = (f"User request: {request}\n\n"
                  f"Your previous recipe (JSON):\n{plan.model_dump_json(indent=2)}\n\n"
                  "The Pantry Verifier rejected it for these reasons:\n"
                  + "\n".join(f"- {issue}" for issue in verdict.issues)
                  + "\n\nReturn a corrected recipe that fixes every issue.")
        result = await run_with_approvals(self.recipe_planner, prompt, self.approve)
        return result.final_output_as(RecipePlan)


def format_recipe_reply(attempts: list[Attempt]) -> str:
    final = attempts[-1]
    plan = final.plan
    if not plan.recipe_name:
        return plan.note or "I couldn't find a recipe you can make with what's in the pantry."

    lines = [f"**{plan.recipe_name}** ({plan.servings} servings)", "", "Ingredients:"]
    lines += [f"- {i.item}: {i.quantity:g} {i.unit}" for i in plan.ingredients]
    lines += ["", "Steps:"]
    lines += [f"{n}. {step}" for n, step in enumerate(plan.steps, 1)]
    if plan.note:
        lines += ["", plan.note]
    if final.verdict and not final.verdict.passed:
        lines += ["", f"Heads up: this still didn't pass the pantry check after "
                      f"{MAX_REVISIONS} revisions:"]
        lines += [f"- {issue}" for issue in final.verdict.issues]
    return "\n".join(lines)
