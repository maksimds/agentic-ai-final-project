"""Tests that run without Azure: the pantry logic, plus the approval guardrail
exercised through the real Agents SDK runner with a scripted stand-in model."""

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

from pantrypal import pantry_store
from pantrypal.pantry_keeper import build_pantry_keeper
from pantrypal.runner import run_turn

set_tracing_disabled(True)


@pytest.fixture(autouse=True)
def temp_pantry(tmp_path, monkeypatch):
    monkeypatch.setenv("PANTRY_FILE", str(tmp_path / "pantry.json"))
    monkeypatch.setenv("PANTRY_TODAY", "2026-11-03")
    pantry_store.reset_pantry()


# ---------- pantry logic ----------

def test_read_pantry_reports_days_since_purchase():
    items = pantry_store.read_pantry()["items"]
    assert items["milk"]["days_since_purchase"] == 6


def test_add_existing_item():
    out = pantry_store.update_item("Eggs", 12)
    assert out == {"item": "eggs", "action": "added", "before": 9, "after": 21}


def test_new_item_needs_unit():
    with pytest.raises(ValueError, match="unit is required"):
        pantry_store.update_item("tortillas", 10)
    assert pantry_store.update_item("tortillas", 10, unit="count")["after"] == 10


def test_cannot_remove_more_than_on_hand():
    with pytest.raises(ValueError, match="cannot remove"):
        pantry_store.update_item("onion", -5)


def test_using_everything_removes_item():
    pantry_store.update_item("garlic", -1)
    assert "garlic" not in pantry_store.read_pantry()["items"]


def test_unit_mismatch_rejected():
    with pytest.raises(ValueError, match="tracked in lb"):
        pantry_store.update_item("chicken breast", 16, unit="oz")


def test_check_restock_finds_low_and_old_items():
    needs = {e["item"] for e in pantry_store.check_restock()["needs_restock"]}
    # milk: at restock level and 6 days old; butter: 1 stick (restock at 1)
    assert needs == {"milk", "butter"}


def test_grocery_list_adds_extras_without_duplicates():
    out = pantry_store.build_grocery_list(["Bread", "milk"])
    names = [e["item"] for e in out["grocery_list"]]
    assert names == ["bread", "butter", "milk"]


# ---------- approval guardrail through the SDK ----------

class ScriptedModel(Model):
    """Stands in for Azure: first asks to add 2 gallons of milk, then replies."""

    def __init__(self):
        self.calls = 0

    async def get_response(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            out = [ResponseFunctionToolCall(
                type="function_call", call_id="call_1", name="update_pantry",
                arguments=json.dumps({"item": "milk", "change": 2}),
            )]
        else:
            out = [ResponseOutputMessage(
                id="msg_1", type="message", role="assistant", status="completed",
                content=[ResponseOutputText(type="output_text", text="Done.", annotations=[])],
            )]
        return ModelResponse(output=out, usage=Usage(), response_id=None)

    def stream_response(self, *args, **kwargs):
        raise NotImplementedError


def _milk():
    return pantry_store.read_pantry()["items"]["milk"]["quantity"]


def test_update_blocked_when_user_rejects():
    agent = build_pantry_keeper(ScriptedModel())
    asked = []
    reply, _ = asyncio.run(run_turn(agent, [], "I bought 2 gallons of milk",
                                    approve=lambda n, a: asked.append((n, a)) or False))
    assert asked == [("update_pantry", {"item": "milk", "change": 2})]
    assert _milk() == 0.25  # unchanged
    assert reply == "Done."


def test_update_applied_when_user_approves():
    agent = build_pantry_keeper(ScriptedModel())
    asyncio.run(run_turn(agent, [], "I bought 2 gallons of milk", approve=lambda n, a: True))
    assert _milk() == 2.25
