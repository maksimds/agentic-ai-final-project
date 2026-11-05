"""Chat with the full PantryPal system (Kitchen Coordinator + all agents).

    python run_pantrypal.py                         # interactive chat
    python run_pantrypal.py "what can I cook?"      # one question, then exit
    python run_pantrypal.py --reset                 # restore the demo pantry first
    python run_pantrypal.py --trace                 # also show routing and verifier results
"""

from __future__ import annotations

import asyncio
import sys

from pantrypal import pantry_store
from pantrypal.config import get_model
from pantrypal.orchestrator import PantryPal, TurnResult


def show(turn: TurnResult, trace: bool) -> None:
    if trace:
        print(f"\n  [route] {turn.route}")
        for n, attempt in enumerate(turn.attempts, 1):
            v = attempt.verdict
            status = "no recipe" if v is None else ("PASS" if v.passed else "FAIL")
            print(f"  [draft {n}] {attempt.plan.recipe_name or '-'}: {status}")
            for issue in (v.issues if v else []):
                print(f"      - {issue}")
    print(f"\nPantryPal: {turn.reply}")


async def main(args: list[str]) -> None:
    if "--reset" in args:
        pantry_store.reset_pantry()
        print("Pantry reset to demo data.")
    trace = "--trace" in args
    args = [a for a in args if a not in {"--reset", "--trace"}]

    app = PantryPal(get_model())

    if args:
        show(await app.handle(" ".join(args)), trace)
        return

    print("PantryPal ready. Type 'quit' to exit.")
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
            show(await app.handle(message), trace)
        except Exception as err:  # show failures instead of inventing an answer
            print(f"\n[error] {type(err).__name__}: {err}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
