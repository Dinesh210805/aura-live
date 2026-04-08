---
last_verified: 2026-04-08
source_files: [agents/coordinator.py, agents/commander.py, agents/planner_agent.py, agents/actor_agent.py, agents/responder.py, agents/validator.py, agents/verifier_agent.py, agents/perceiver_agent.py]
status: current
---

# Agents — Overview & Interaction Map

**Directory**: `agents/`

---

## The 9 Agents

AURA's automation pipeline is split into exactly 9 single-responsibility agents. The `Coordinator` is the only orchestrator — all others are workers that it calls.

| # | Agent | File | LLM Calls | Role |
|---|-------|------|-----------|------|
| 1 | `Commander` | `agents/commander.py` | Optional (fallback only) | Intent parsing |
| 2 | `Planner` | `agents/planner_agent.py` | Yes | Goal decomposition |
| 3 | `Coordinator` | `agents/coordinator.py` | Yes | Main execution loop |
| 4 | `Perceiver` | `agents/perceiver_agent.py` | Via VLM | Screen perception |
| 5 | `Actor` | `agents/actor_agent.py` | **None** | Gesture execution |
| 6 | `Responder` | `agents/responder.py` | Yes | Natural language response |
| 7 | `Validator` | `agents/validator.py` | **None** | Pre-execution validation |
| 8 | `Verifier` | `agents/verifier_agent.py` | Yes | Post-action verification |
| 9 | `VisualLocator` | `perception/vlm_selector.py` | Yes (VLM) | SoM element selection |

---

## Interaction Map

```
        User Voice
            │
            ▼
       Commander ──(intent)──► Coordinator
                                    │
                         ┌──────────┼──────────┐
                         ▼          ▼          ▼
                      Planner   Perceiver   Validator
                    (skeleton)  (screen)   (pre-check)
                         │          │          │
                         └──────────┴──────────┘
                                    │
                                    ▼
                                  Actor
                              (zero LLM calls)
                                    │
                                    ▼
                                 Verifier ──► VisualLocator
                                    │
                                    ▼
                                Responder ──► TTS
```

---

## Design Rules

1. **No agent calls another agent directly** — all coordination goes through `Coordinator`
2. **`Actor` and `Validator` have zero LLM calls** — deterministic by design
3. **`Coordinator` is the only stateful agent** — others are stateless per-call
4. **Circular dependency pattern**: `Perceiver` is created first (no controller), then `PerceptionController(screen_vlm=perceiver)` is created, then `perceiver.perception_controller = controller` is set back

---

## Initialization Order in `compile_aura_graph()`

```python
# 1. Create services
llm_service = LLMService()
vlm_service = VLMService()
tts_service = TTSService()
stt_service = STTService()

# 2. Create agents (no circular deps yet)
commander = CommanderAgent(llm_service)
responder = ResponderAgent(llm_service, tts_service)
validator = ValidatorAgent()
actor = ActorAgent(gesture_executor, policy_engine)
planner = PlannerAgent(llm_service)
perceiver = PerceiverAgent(vlm_service, perception_pipeline)

# 3. Wire circular dependency
controller = PerceptionController(screen_vlm=perceiver)
perceiver.perception_controller = controller

# 4. Create coordinator (needs all others)
coordinator = CoordinatorAgent(
    planner, perceiver, actor, validator,
    verifier, responder, reactive_gen
)
```

---

## Per-Agent Pages

- [commander.md](commander.md)
- [planner.md](planner.md)
- [coordinator.md](coordinator.md)
- [perceiver.md](perceiver.md)
- [actor.md](actor.md)
- [responder.md](responder.md)
- [validator.md](validator.md)
- [verifier.md](verifier.md)
- [visual_locator.md](visual_locator.md)
