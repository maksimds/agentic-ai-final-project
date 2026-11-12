"""Orchestrator tests that run without Azure. One scripted stand-in model is
shared by all four agents and replays its responses in order, so each test
reads as the exact sequence of model turns across the whole system."""

from __future__ import annotations

import asyncio
import json

import pytest
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from agents import Usage, set_tracing_disabled
from agents.items import ModelResponse
from agents.models.interface import Model

from pantrypal import pantry_store, recipe_book
from pantrypal.orchestrator import MAX_REVISIONS, PantryPal

set_tracing_disabled(True)


@pytest.fixture(autouse=True)
def temp_pantry(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTRY_FILE", str(tmp_path / "pantry.json"))
    monkeypatch.setenv("PANTRY_TODAY", "2026-11-03")
    pantry_store.reset_pantry()


def call(name: str, **args):
    return ResponseFunctionToolCall(type="function_call", call_id=f"call_{name}",
                                    name=name, arguments=json.dumps(args))


def say(text: str):
    return ResponseOutputMessage(
        id="msg", type="message", role="assistant", status="completed",
        content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
    )


class ScriptedModel(Model):
    def __init__(self, *turns):
        self.turns = list(turns)

    async def get_response(self, *args, **kwargs):
        return ModelResponse(output=[self.turns.pop(0)], usage=Usage(), response_id=None)

    def stream_response(self, *args, **kwargs):
        raise NotImplementedError


def plan(name: str, servings: int = 2) -> str:
    r = recipe_book.scale_recipe(name, servings)
    return json.dumps({"recipe_name": r["name"], "servings": servings,
                       "ingredients": r["ingredients"], "steps": r["steps"], "note": ""})


def verdict(passed: bool, *issues: str) -> str:
    return json.dumps({"passed": passed, "issues": list(issues)})


def run(app: PantryPal, message: str):
    return asyncio.run(app.handle(message))


# ---------- routing ----------

def test_coordinator_answers_out_of_scope_itself():
    app = PantryPal(ScriptedModel(say("I only handle pantry, groceries and recipes.")))
    turn = run(app, "What's the capital of France?")
    assert turn.route == "coordinator"
    assert "only handle" in turn.reply


def test_pantry_route_keeps_approval_guardrail():
    model = ScriptedModel(
        call("transfer_to_pantry_keeper"),          # coordinator routes
        call("update_pantry", item="milk", change=2),  # keeper tries to change data
        say("OK, I left the milk as is."),
    )
    asked = []
    app = PantryPal(model, approve=lambda n, a: asked.append(n) or False)
    turn = run(app, "I bought 2 gallons of milk")
    assert turn.route == "pantry"
    assert asked == ["update_pantry"]
    assert pantry_store.read_pantry()["items"]["milk"]["quantity"] == 0.25  # unchanged


def test_history_carries_across_turns():
    app = PantryPal(ScriptedModel(say("Which one, pantry or recipes?"), say("Got it.")))
    run(app, "help")
    run(app, "pantry")
    users = [m["content"] for m in app.history if m.get("role") == "user"]
    assert users == ["help", "pantry"]


# ---------- evaluator-optimizer loop ----------

def test_failed_recipe_is_revised_until_it_passes():
    model = ScriptedModel(
        call("transfer_to_recipe_planner"),
        say(plan("Chicken Noodle Soup")),           # draft 1: needs carrots, celery...
        say(verdict(False, "carrots: not in the pantry")),
        say(plan("Garlic Butter Chicken and Rice")),  # draft 2
        say(verdict(True)),
    )
    app = PantryPal(model)
    turn = run(app, "What can I make for dinner?")
    assert turn.route == "recipe"
    assert [a.plan.recipe_name for a in turn.attempts] == [
        "Chicken Noodle Soup", "Garlic Butter Chicken and Rice"]
    assert [a.verdict.passed for a in turn.attempts] == [False, True]
    assert turn.reply.startswith("**Garlic Butter Chicken and Rice**")
    assert "Heads up" not in turn.reply
    # only the final answer goes into shared history, not drafts or verdicts
    assert app.history[-1] == {"role": "assistant", "content": turn.reply}


def test_revisions_are_capped():
    bad = [say(plan("Chicken Noodle Soup")), say(verdict(False, "carrots: not in the pantry"))]
    model = ScriptedModel(call("transfer_to_recipe_planner"), *bad * (MAX_REVISIONS + 1))
    turn = run(PantryPal(model), "Make me soup")
    assert len(turn.attempts) == MAX_REVISIONS + 1
    assert "Heads up" in turn.reply and "carrots" in turn.reply
    assert model.turns == []  # no extra model calls past the cap


def test_no_recipe_skips_verifier():
    empty = json.dumps({"recipe_name": "", "servings": 2, "ingredients": [], "steps": [],
                        "note": "Nothing in the recipe book fits; you're out of chicken."})
    turn = run(PantryPal(ScriptedModel(call("transfer_to_recipe_planner"), say(empty))),
               "chicken recipe?")
    assert turn.attempts[0].verdict is None
    assert "out of chicken" in turn.reply


# ---------- deterministic recipe checks ----------

def test_scale_recipe_multiplies_amounts():
    eggs = recipe_book.scale_recipe("Cheesy Scrambled Eggs", 4)["ingredients"][0]
    assert eggs == {"item": "eggs", "quantity": 8, "unit": "count"}


def test_check_against_pantry_reports_problems():
    soup = recipe_book.scale_recipe("Chicken Noodle Soup", 2)["ingredients"]
    problems = recipe_book.check_against_pantry(soup)["problems"]
    assert "carrots: not in the pantry" in problems
    assert recipe_book.check_against_pantry(
        recipe_book.scale_recipe("Garlic Butter Chicken and Rice", 2)["ingredients"]
    )["all_available"]


def test_cookable_recipes_with_demo_pantry():
    assert recipe_book.cookable_recipes(2) == [
        "Cheesy Scrambled Eggs", "Garlic Butter Chicken and Rice",
        "Cheesy Baked Chicken with Tomato Sauce", "Creamy Cheddar Rice"]
