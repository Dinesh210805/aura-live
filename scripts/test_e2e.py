"""
End-to-end agent pipeline test.

Runs three tiers of testing:
  1. Commander — intent parsing (LLM call, no device)
  2. Graph smoke — full pipeline via execute_aura_task_from_text
     (graph + coordinator + actor; device calls will fail gracefully
      since no Android device is connected, but we verify the pipeline
      doesn't crash before reaching the actor)
  3. Reflexion — lesson write + read round-trip
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import get_settings
from services.llm import LLMService
from agents.commander import CommanderAgent

settings = get_settings()
llm = LLMService(settings)

# ─── colour helpers ──────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):  print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def info(msg): print(f"  {CYAN}·{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{CYAN}{'-'*60}{RESET}\n{BOLD}{msg}{RESET}\n{'-'*60}")


# ─── TIER 1: Commander intent parsing ────────────────────────────────────────
COMMANDER_CASES = [
    # (utterance, expected_action_contains)
    ("open WhatsApp",                   "open_app"),
    ("send hi to John",                 "send_message"),
    ("call Mom",                        "make_call"),
    ("scroll down",                     "scroll"),
    ("take a screenshot",               "screenshot"),
    ("play Blinding Lights on Spotify", "open_app"),      # routes as open_app + play_specific_track param
    ("what is on my screen",            "read_screen"),   # actual action name is read_screen
    ("go back",                         "back"),          # actual action name is back
    ("hey can you open Instagram please","open_app"),
    ("hello",                           None),   # conversational — any action OK
]

def test_commander():
    header("TIER 1 — Commander Agent (intent parsing)")
    agent = CommanderAgent(llm)
    passed = failed = 0

    for utterance, expected in COMMANDER_CASES:
        t0 = time.perf_counter()
        try:
            result = agent.parse_intent(utterance)
            ms = (time.perf_counter() - t0) * 1000
            action_ok = (expected is None) or (expected in result.action)
            if action_ok:
                ok(f"{utterance!r:50s}  →  {result.action}  ({ms:.0f}ms, conf={result.confidence:.2f})")
                passed += 1
            else:
                fail(f"{utterance!r:50s}  →  {result.action}  (expected '{expected}', conf={result.confidence:.2f})")
                failed += 1
        except Exception as e:
            fail(f"{utterance!r:50s}  →  EXCEPTION: {e}")
            failed += 1

    print(f"\n  Commander: {GREEN}{passed} passed{RESET}, {RED if failed else GREEN}{failed} failed{RESET}")
    return failed == 0


# ─── TIER 2: Graph pipeline smoke test ───────────────────────────────────────
GRAPH_SMOKE_CASES = [
    # Simple conversational — should return a spoken_response without crashing
    ("hello",               ["spoken_response"]),
    ("what can you do",     ["spoken_response"]),
    # Device command — will fail at actor (no device), but pipeline must not crash
    # and must produce spoken_response with an error/retry message
    ("open WhatsApp",       ["spoken_response", "status"]),
]

async def test_graph_pipeline():
    header("TIER 2 — Graph Pipeline Smoke Test (no Android device)")

    try:
        from aura_graph.graph import compile_aura_graph, execute_aura_task_from_text
    except ImportError as e:
        fail(f"Import failed: {e}")
        return False

    info("Compiling graph (takes ~5s for service init)...")
    t0 = time.perf_counter()
    try:
        app = compile_aura_graph()
        info(f"Graph compiled in {(time.perf_counter()-t0):.1f}s")
    except Exception as e:
        fail(f"Graph compilation failed: {e}")
        import traceback; traceback.print_exc()
        return False

    passed = failed = 0
    for text, expected_keys in GRAPH_SMOKE_CASES:
        info(f"Running: {text!r}")
        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                execute_aura_task_from_text(app, text, thread_id="e2e_test"),
                timeout=30,
            )
            ms = (time.perf_counter() - t0) * 1000
            missing = [k for k in expected_keys if not result.get(k)]
            if not missing:
                spoken = (result.get("spoken_response") or "")[:80]
                ok(f"{text!r:30s} ({ms:.0f}ms) → {spoken!r}")
                passed += 1
            else:
                fail(f"{text!r:30s} missing keys: {missing}  result_keys={list(result.keys())}")
                failed += 1
        except asyncio.TimeoutError:
            fail(f"{text!r:30s} TIMEOUT (>30s)")
            failed += 1
        except Exception as e:
            fail(f"{text!r:30s} EXCEPTION: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n  Graph pipeline: {GREEN}{passed} passed{RESET}, {RED if failed else GREEN}{failed} failed{RESET}")
    return failed == 0


# ─── TIER 3: Reflexion service round-trip ────────────────────────────────────
async def test_reflexion():
    header("TIER 3 — Reflexion Service (lesson write + read)")
    from services.reflexion_service import ReflexionService
    from agents.coordinator import StepMemory

    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp())
    try:
        svc = ReflexionService(llm_service=llm, storage_path=tmp)

        # Fake step history — all positional args required by StepMemory
        steps = [
            StepMemory(
                subgoal_description="open WhatsApp", action_type="open_app",
                target="WhatsApp", result="app_not_found",
                screen_type="home", screen_before="home_screen",
                screen_after="home_screen", screen_description="Home screen visible",
            ),
            StepMemory(
                subgoal_description="tap WhatsApp icon", action_type="tap",
                target="WhatsApp icon", result="element_not_found",
                screen_type="home", screen_before="home_screen",
                screen_after="home_screen",
                screen_description="Home screen, no WhatsApp icon visible",
            ),
        ]

        goal = "open WhatsApp and send hi to John"
        info(f"Generating reflexion lesson for: {goal!r}")
        t0 = time.perf_counter()
        lesson = await svc.generate_lesson(goal, steps, failure_reason="element_not_found after 3 retries")
        ms = (time.perf_counter() - t0) * 1000

        if lesson:
            ok(f"Lesson generated ({ms:.0f}ms): {lesson[:100]!r}")
        else:
            fail("No lesson returned (empty string)")
            return False

        # Round-trip: read it back
        lessons = await svc.get_lessons_for_goal(goal)
        if lessons:
            ok(f"Lesson retrieved ({len(lessons)} lesson(s) for goal bucket)")
        else:
            fail("get_lessons_for_goal returned empty list after write")
            return False

        # Verify bucket key — "launch Telegram" should share "open WhatsApp" lesson pool (both → open_app)
        goal2 = "launch Telegram"
        lessons2 = await svc.get_lessons_for_goal(goal2)
        if lessons2:
            ok(f"Bucket sharing — 'launch Telegram' shares open_app pool ({len(lessons2)} lesson(s))")
        else:
            # Diagnose: show what key each goal maps to
            k1 = svc._goal_key(goal)
            k2 = svc._goal_key(goal2)
            fail(f"Bucket sharing failed — '{goal}' → '{k1}', '{goal2}' → '{k2}' (expected same)")
            return False

        print(f"\n  Reflexion: {GREEN}3/3 passed{RESET}")
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─── main ─────────────────────────────────────────────────────────────────────
async def main():
    print(f"\n{BOLD}AURA E2E Agent Pipeline Test{RESET}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    # Tier 1 — synchronous
    results["commander"] = test_commander()

    # Tier 2 — async graph
    results["graph"] = await test_graph_pipeline()

    # Tier 3 — async reflexion
    results["reflexion"] = await test_reflexion()

    # ─ summary ─
    header("SUMMARY")
    all_pass = True
    for tier, passed in results.items():
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  {tier:20s}  {status}")
        if not passed:
            all_pass = False

    if all_pass:
        print(f"\n{GREEN}{BOLD}All tiers passed.{RESET}\n")
        sys.exit(0)
    else:
        print(f"\n{RED}{BOLD}Some tiers failed — see above.{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
