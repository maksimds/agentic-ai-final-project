"""Run an agent turn, pausing for human approval on any tool that needs it."""

from __future__ import annotations

import json
from typing import Callable

from agents import Agent, Runner


def ask_in_terminal(tool_name: str, arguments: dict) -> bool:
    print(f"\n  [approval needed] {tool_name}({json.dumps(arguments)})")
    return input("  Approve this change? (y/n): ").strip().lower() in {"y", "yes"}


async def run_with_approvals(agent: Agent, run_input,
                             approve: Callable[[str, dict], bool] = ask_in_terminal):
    """Run an agent to completion, asking `approve` about every tool call that
    needs human approval. Works across handoffs: the run resumes with whichever
    agent was active when it paused."""
    result = await Runner.run(agent, run_input)

    while result.interruptions:
        state = result.to_state()
        for item in result.interruptions:
            args = json.loads(item.arguments or "{}")
            if approve(item.tool_name or item.name, args):
                state.approve(item)
            else:
                state.reject(item)
        result = await Runner.run(agent, state)

    return result


async def run_turn(agent: Agent, history: list, user_message: str,
                   approve: Callable[[str, dict], bool] = ask_in_terminal):
    """Send one user message, handle approvals, return (reply, updated_history).

    `history` is the conversation so far; passing it back in each turn is what
    gives the agent memory across turns within a session.
    """
    result = await run_with_approvals(
        agent, history + [{"role": "user", "content": user_message}], approve)
    return result.final_output, result.to_input_list()
