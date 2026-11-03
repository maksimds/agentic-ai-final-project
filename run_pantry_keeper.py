"""Chat with the Pantry Keeper agent.

    python run_pantry_keeper.py                    # interactive chat
    python run_pantry_keeper.py "what is low?"     # one question, then exit
    python run_pantry_keeper.py --reset            # restore the demo pantry first
"""

from __future__ import annotations

import asyncio
import sys

from pantrypal import pantry_store
from pantrypal.config import get_model
from pantrypal.pantry_keeper import build_pantry_keeper
from pantrypal.runner import run_turn


async def main(args: list[str]) -> None:
    if "--reset" in args:
        pantry_store.reset_pantry()
        print("Pantry reset to demo data.")
        args = [a for a in args if a != "--reset"]

    agent = build_pantry_keeper(get_model())
    history: list = []

    if args:
        reply, _ = await run_turn(agent, history, " ".join(args))
        print(f"\nPantry Keeper: {reply}")
        return

    print("Pantry Keeper ready. Type 'quit' to exit.")
    while True:
        try:
            message = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() in {"quit", "exit"}:
            break
        if not message:
            continue
        try:
            reply, history = await run_turn(agent, history, message)
        except Exception as err:  # show failures instead of inventing an answer
            print(f"\n[error] {type(err).__name__}: {err}")
            continue
        print(f"\nPantry Keeper: {reply}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
