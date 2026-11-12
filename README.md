# PantryPal

A multi-agent pantry assistant built with the OpenAI Agents SDK on Azure OpenAI via APIM.
It tracks what is in your kitchen, builds grocery lists, and (soon) suggests recipes that
only use what you have.

## Agents

| Agent | Role | Status |
|---|---|---|
| Pantry Keeper | Inventory manager; the only agent that can change pantry data | **Working** |
| Kitchen Coordinator | Routes user requests to the right agent (SDK handoffs) | **Working (first version)** |
| Recipe Planner | Suggests recipes from pantry contents, scaled to servings | Starter version (no `get_preferences` yet) |
| Pantry Verifier | Checks each recipe against the pantry (evaluator-optimizer loop) | Starter version |

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in your Azure / APIM values
```

`.env` is in `.gitignore`. Never commit keys. No native OpenAI key is used anywhere.

## Run the full system (orchestrator)

```bash
python run_pantrypal.py --reset --trace              # interactive, shows routing + verifier drafts
python run_pantrypal.py "What can I make for dinner?"
```

How a turn flows (`pantrypal/orchestrator.py`):

1. **Routing.** The Kitchen Coordinator hands off to the Pantry Keeper or the Recipe Planner,
   or answers itself (clarifying question, out of scope). Every turn starts at the Coordinator.
2. **Human in the loop.** All runs go through `run_with_approvals`, so `update_pantry`
   still pauses for `y/n` after a handoff.
3. **Evaluator-optimizer.** When the Recipe Planner answers, code (not a prompt) sends its
   structured `RecipePlan` to the Pantry Verifier. A fail sends the issues back to the planner,
   at most `MAX_REVISIONS = 2` times. Only the final answer is kept in the chat history.

Recipes come from `data/recipes.json`, transcribed from `notes/notes.pdf`. The "is it in the
pantry?" check (`recipe_book.check_against_pantry`) is plain code the verifier calls as a tool.

## Run the Pantry Keeper on its own

```bash
python run_pantry_keeper.py --reset                  # start from the demo pantry
python run_pantry_keeper.py "What's running low?"    # one question
python run_pantry_keeper.py                          # interactive chat (memory across turns)
```

### Things to try

| Input | Expected behavior |
|---|---|
| `What's in my pantry?` | Calls `read_pantry`, lists all 9 demo items with quantities |
| `What's running low?` | Calls `check_restock`; flags milk (low and 6+ days old) and butter |
| `Make me a grocery list and add bread` | Calls `build_grocery_list`; returns bread, butter, milk |
| `I bought a dozen eggs` | Calls `update_pantry`; the program pauses and asks `Approve this change? (y/n)`. Answer `n` and the pantry is unchanged; answer `y` and eggs go from 9 to 21 |
| `I used 3 onions`, then `how many onions are left?` | Shows memory across turns within a session |
| `What's the capital of France?` | Declines; outside its scope |

Results depend on today's date (shelf-life checks). Set `PANTRY_TODAY=2026-11-03` in `.env` to reproduce the table above exactly.

## Tests

The tests run without Azure. They cover the pantry logic and the approval guardrail
(through the real SDK runner, with a scripted stand-in model).

```bash
python -m pytest -q
```

## Layout

```
pantrypal/
  config.py          Azure OpenAI / APIM client (reads .env)
  pantry_store.py    pantry data logic (JSON file, persists between sessions)
  pantry_keeper.py   Pantry Keeper agent and its 4 tools
  recipe_book.py     recipe data, scaling, and the pantry check (plain Python)
  recipe_planner.py  Recipe Planner agent (structured RecipePlan output)
  pantry_verifier.py Pantry Verifier agent (structured Verdict output)
  kitchen_coordinator.py  Kitchen Coordinator agent (router, handoffs only)
  orchestrator.py    PantryPal class: routing -> approvals -> verify/revise loop
  runner.py          runs an agent and pauses for human approval
data/pantry_seed.json  demo pantry
data/recipes.json      recipe book (from notes/notes.pdf)
run_pantrypal.py       full-system command-line entry point
run_pantry_keeper.py   Pantry Keeper-only entry point
tests/
```
