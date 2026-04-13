"""
LangGraph state machine assembly for the AURA backend.

This module creates the complete task execution graph by connecting
all nodes and edges into a runnable state machine.

TRI-PROVIDER PARALLEL ARCHITECTURE:
- Fan-out after intent parsing: UI capture + validation run in parallel
- Fan-in before planning: merge parallel results
- Model routing: Groq for speed, vision/reasoning, Gemini as fallback
"""

import asyncio
import time
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from utils.logger import get_logger
from services.command_logger import create_new_execution_logger, clear_execution_logger

from .edges import (
    route_from_start,
    should_continue_after_error_handling,
    should_continue_after_intent_parsing,
    should_continue_after_perception,
    should_continue_after_speak,
    should_continue_after_stt,
)
from .core_nodes import (
    error_handler_node,
    execute_node,
    initialize_nodes,
    parse_intent_node,
    speak_node,
    stt_node,
)

# Import from nodes package (specialized goal-driven nodes)
from .nodes import perception_node

from aura_graph.nodes.coordinator_node import (
    coordinator_node,
    initialize_coordinator,
)
from aura_graph.nodes.web_search_node import web_search_node

from .state import TaskState

logger = get_logger(__name__)


def _create_initial_state(
    input_type: str,
    raw_audio: bytes = None,
    transcript: str = "",
    streaming_transcript: str = "",
    config: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Create initial task state with only essential fields."""
    import uuid
    session_id = str(uuid.uuid4())[:8]
    
    return {
        "session_id": session_id,
        "raw_audio": raw_audio,
        "transcript": transcript,
        "streaming_transcript": streaming_transcript,
        "input_type": input_type,
        "intent": None,
        "ui_screenshot": None,
        "ui_elements": [],
        "plan": [],
        "executed_steps": [],
        "current_step": 0,
        "status": "starting",
        "feedback_message": "",
        "error_message": None,
        "retry_count": 0,
        "max_retries": 3,
        # Explicitly reset per-task fields so LangGraph checkpointing does not
        # bleed values from the previous task in the same session thread.
        "goal_summary": None,
        "agent_state": None,
        "start_time": time.time(),
        "end_time": None,
        "execution_time": 0.0,
        "execution_mode": config.get("execution_mode", "live") if config else "live",
        "task_id": f"{input_type}_{int(time.time() * 1000)}",
        "workflow_steps": [] if config and config.get("track_workflow") else None,
        "track_workflow": config.get("track_workflow", False) if config else False,
    }


def create_aura_graph() -> StateGraph:
    """
    Create and configure the complete AURA task execution graph.

    PARALLEL ARCHITECTURE:
    ```
    STT → Parse Intent → [Fan-Out] → UI Analysis  → [Fan-In] → Plan → Execute → Speak
                              ↘                   ↗
                               → Validation     →
    ```

    The fan-out allows UI analysis and validation to run concurrently,
    reducing total latency when both operations are needed.

    Returns:
        Compiled StateGraph ready for execution.
    """
    try:
        logger.info("Creating AURA task execution graph (parallel architecture)")

        # Initialize the state graph with TaskState schema
        graph = StateGraph(TaskState)

        # Add all nodes to the graph
        logger.info("Adding nodes to graph")
        graph.add_node("stt", stt_node)
        graph.add_node("parse_intent", parse_intent_node)
        graph.add_node("perception", perception_node)
        graph.add_node("execute", execute_node)
        graph.add_node("speak", speak_node)
        graph.add_node("error_handler", error_handler_node)
        
        # Coordinator node - multi-agent execution
        graph.add_node("coordinator", coordinator_node)

        # Web search node - real-time Tavily lookups (weather, news, facts)
        graph.add_node("web_search", web_search_node)

        # Set conditional entry point that routes based on input type
        # Note: We use only add_conditional_edges from __start__, not set_entry_point
        # Using both causes duplicate execution issues
        logger.info("Setting conditional entry point")
        graph.add_conditional_edges(
            "__start__",
            route_from_start,
            {
                "stt": "stt",
                "parse_intent": "parse_intent",
                "error_handler": "error_handler",
            },
        )

        # Add conditional edges from STT
        graph.add_conditional_edges(
            "stt",
            should_continue_after_stt,
            {"parse_intent": "parse_intent", "error_handler": "error_handler"},
        )

        # Add conditional edges from intent parsing
        graph.add_conditional_edges(
            "parse_intent",
            should_continue_after_intent_parsing,
            {
                "perception": "perception",
                "speak": "speak",
                "error_handler": "error_handler",
                "coordinator": "coordinator",
                "web_search": "web_search",
            },
        )

        # Web search node feeds directly into speak (answer → TTS)
        graph.add_edge("web_search", "speak")

        # Add conditional edges from perception
        graph.add_conditional_edges(
            "perception",
            should_continue_after_perception,
            {
                "speak": "speak",
                "error_handler": "error_handler",
                "coordinator": "coordinator",  # Multi-agent execution path
            },
        )

        # Coordinator edges (multi-agent execution path)
        graph.add_edge("coordinator", "speak")

        # Add conditional edges from error handler
        graph.add_conditional_edges(
            "error_handler",
            should_continue_after_error_handling,
            {
                "perception": "perception",
                "speak": "speak",
                END: END
            },
        )

        # Add edge from speak to end
        graph.add_conditional_edges("speak", should_continue_after_speak, {END: END})

        logger.info(
            "Graph structure created successfully (parallel architecture enabled)"
        )
        return graph

    except Exception as e:
        logger.error(f"Failed to create graph: {e}")
        raise


async def _finalize_and_upload(cmd_logger: Any, status: str, task_id: str, result: dict) -> None:
    """Finalize the execution log, upload to GCS, and clear the logger.

    Shared by all execute_aura_task_* entry points to avoid copy-paste.
    All errors are non-fatal — failures here must never mask the real result.
    """
    try:
        cmd_logger.finalize(status=status)
    except Exception as finalize_err:
        logger.error(f"Failed to finalize command log: {finalize_err}")

    try:
        log_path = cmd_logger.get_log_file_path()
        if log_path:
            result["local_log_path"] = str(log_path)
            logger.info(f"Execution log saved: {log_path}")
    except Exception as path_err:
        logger.warning(f"Could not retrieve log file path: {path_err}")

    try:
        from gcs_log_uploader import upload_log_to_gcs_async
        log_path = cmd_logger.get_log_file_path()
        log_url = await upload_log_to_gcs_async(log_path, task_id)
        if log_url:
            result["log_url"] = log_url
            logger.info(f"Execution log available at: {log_url}")
    except Exception as gcs_err:
        logger.warning(f"GCS log upload skipped: {gcs_err}")
    finally:
        clear_execution_logger()


def compile_aura_graph(checkpointer: Any = None) -> Any:
    """
    Compile the AURA graph into a runnable application.
    Initializes all services and agents before compilation.

    HYBRID ARCHITECTURE INITIALIZATION:
    - Groq services: LLM (fast intent), STT (Whisper Turbo), TTS
    - Gemini services: VLM (vision), Planning (reasoning)
    - Agents: Commander, Navigator, Responder, Screen Reader, Validator

    Args:
        checkpointer: Optional checkpointer for state persistence.

    Returns:
        Compiled graph ready for execution.
    """
    try:
        logger.info("Compiling AURA graph (hybrid parallel architecture)")

        # Initialize services and agents before compilation
        from agents.commander import CommanderAgent
        from agents.responder import ResponderAgent
        from agents.validator import ValidatorAgent
        from config.settings import get_settings
        from services.llm import LLMService
        from services.real_accessibility import real_accessibility_service
        from services.stt import STTService
        from services.tts import TTSService
        from services.vlm import VLMService

        settings = get_settings()

        # Initialize services
        stt_service = STTService(settings)
        llm_service = LLMService(settings)
        vlm_service = VLMService(settings)
        tts_service = TTSService(settings)

        # Initialize device executor (no settings parameter needed)
        from services.real_device_executor import real_device_executor

        device_executor_service = real_device_executor

        # Initialize agents (Tri-Provider Architecture)
        # Commander: Fast intent parsing (Groq - llama-3.1-8b-instant)
        commander_agent = CommanderAgent(llm_service=llm_service)

        # Navigator: DEPRECATED - UniversalAgent now handles all actions
        # Kept as None for backward compatibility with initialize_nodes

        # Responder: Feedback generation (Groq - fast for TTS)
        responder_agent = ResponderAgent(
            llm_service=llm_service, tts_service=tts_service
        )

        # Validator: Intent pre-validation (fast, minimal model use)
        validator_agent = ValidatorAgent()

        # Initialize Coordinator (Phase 3 - Multi-agent architecture)
        from agents.coordinator import Coordinator
        from agents.planner_agent import PlannerAgent
        from agents.perceiver_agent import PerceiverAgent
        from agents.actor_agent import ActorAgent
        from agents.verifier_agent import VerifierAgent
        from services.goal_decomposer import GoalDecomposer
        from services.gesture_executor import GestureExecutor
        from services.perception_controller import get_perception_controller
        from perception.perception_pipeline import PerceptionPipeline
        from services.task_progress import get_task_progress_service

        goal_decomposer = GoalDecomposer(llm_service)
        gesture_executor = GestureExecutor()

        planner_agent = PlannerAgent(goal_decomposer)
        perception_pipeline = PerceptionPipeline(vlm_service=vlm_service)

        # Warm up OmniParser in the background so the first real VLM call
        # bears no model-load latency.
        import threading
        threading.Thread(
            target=perception_pipeline.warmup,
            name="omniparser-warmup",
            daemon=True,
        ).start()

        # Construction order: PerceiverAgent first (no controller yet) →
        #   PerceptionController (receives perceiver as screen_vlm) →
        #   wire perceiver_agent.perception_controller back.
        perceiver_agent = PerceiverAgent(
            vlm_service=vlm_service,
            perception_pipeline=perception_pipeline,
        )
        perception_controller = get_perception_controller(screen_vlm=perceiver_agent)
        perceiver_agent.perception_controller = perception_controller
        actor_agent = ActorAgent(gesture_executor)
        verifier_agent = VerifierAgent(perception_controller, llm_service=llm_service)
        task_progress_service = get_task_progress_service()

        from services.reactive_step_generator import ReactiveStepGenerator
        reactive_step_gen = ReactiveStepGenerator(llm_service=llm_service, vlm_service=vlm_service)

        coordinator = Coordinator(
            planner=planner_agent,
            perceiver=perceiver_agent,
            actor=actor_agent,
            verifier=verifier_agent,
            task_progress=task_progress_service,
            reactive_gen=reactive_step_gen,
        )
        initialize_coordinator(coordinator)
        logger.info("  - Coordinator: Initialized (Phase 3 multi-agent execution)")

        # Initialize PromptGuard (safety screening before CommanderAgent)
        from services.prompt_guard import initialize_prompt_guard
        groq_client = llm_service.groq_client
        prompt_guard = initialize_prompt_guard(groq_client, model=settings.safety_model)
        if prompt_guard.available:
            logger.info(f"  - PromptGuard: Initialized ({settings.safety_model} via Groq)")
        else:
            logger.warning("  - PromptGuard: Disabled (no Groq API key)")

        # Initialize nodes with services and agents
        initialize_nodes(
            app_settings=settings,
            app_stt_service=stt_service,
            app_llm_service=llm_service,
            app_vlm_service=vlm_service,
            app_tts_service=tts_service,
            app_accessibility_service=real_accessibility_service,
            app_device_executor_service=device_executor_service,
            app_commander_agent=commander_agent,
            app_responder_agent=responder_agent,
            app_screen_vlm_agent=perceiver_agent,
            app_validator_agent=validator_agent,
        )

        logger.info("Services and agents initialized (tri-provider architecture)")
        logger.info(
            f"  - VLM Provider: {settings.default_vlm_provider} ({settings.default_vlm_model})"
        )
        logger.info(
            f"  - LLM Provider: {settings.default_llm_provider} ({settings.default_llm_model})"
        )
        logger.info(
            f"  - Planning Provider: {settings.planning_provider} ({settings.planning_model})"
        )
        logger.info(f"  - STT Model: {settings.default_stt_model}")
        logger.info(f"  - TTS Provider: {settings.default_tts_provider}")
        logger.info(f"  - Parallel Execution: {settings.enable_parallel_execution}")

        # Create and compile graph
        graph = create_aura_graph()

        # Cross-task memory store: shared across all sessions within this process.
        # Nodes can read/write user facts (e.g. preferred apps, last target) via
        # config["store"] using store.put() / store.search().
        from langgraph.store.memory import InMemoryStore
        store = InMemoryStore()

        # FIXED: FIX-001 — add recursion_limit to prevent GraphRecursionError on retried tasks
        # Formula: 4 nodes/step × 10 steps × 2.5x retry buffer = 100
        if checkpointer:
            app = graph.compile(checkpointer=checkpointer, store=store)
        else:
            app = graph.compile(store=store)

        # --- Agent Registry wiring (feature-gated) ---
        # Register all 9 agents as adapters so they can be invoked via
        # AuraContext.spawn_agent() and AuraQueryEngine. Non-fatal: a failure
        # here must not prevent the graph from running in legacy mode.
        try:
            from aura.registry.agent_registry import get_agent_registry
            from agents.adapters import (
                CommanderAdapter,
                PerceiverAdapter,
                CoordinatorAdapter,
                PlannerAdapter,
                ActorAdapter,
                ResponderAdapter,
                VerifierAdapter,
            )

            registry = get_agent_registry()
            registry.register(CommanderAdapter(commander_agent))
            registry.register(PerceiverAdapter(perceiver_agent))
            registry.register(CoordinatorAdapter(coordinator))
            registry.register(PlannerAdapter(planner_agent))
            registry.register(ActorAdapter(actor_agent))
            registry.register(ResponderAdapter(responder_agent))
            registry.register(VerifierAdapter(verifier_agent))
            logger.info(
                f"[AgentRegistry] Registered {len(registry)} agents: {registry.names()}"
            )
        except Exception as reg_err:
            logger.warning(f"Agent registry wiring failed (non-fatal): {reg_err}")

        logger.info("Graph compiled successfully (parallel architecture enabled)")
        return app

    except Exception as e:
        logger.error(f"Failed to compile graph: {e}")
        raise


async def execute_aura_task_from_streaming(
    app: Any,
    streaming_transcript: str,
    config: Dict[str, Any] = None,
    thread_id: str = None,
    track_workflow: bool = True,
    session_id: str = None,
) -> Dict[str, Any]:
    """
    Execute AURA task from streaming transcript (WebSocket).

    Args:
        app: Compiled graph application.
        streaming_transcript: Final transcript from streaming audio.
        config: Optional execution configuration.
        thread_id: Optional thread ID for state persistence.
        track_workflow: Whether to track workflow steps.
        session_id: Conversation session ID for context tracking (NEW).

    Returns:
        Final task state.
    """
    cmd_logger = None
    try:
        logger.info(
            f"Executing streaming task (thread: {thread_id}, session: {session_id})"
        )

        # Get or create conversation session (NEW)
        from services.conversation_session import get_session_manager

        session_manager = get_session_manager()

        # Use thread_id as session_id if not provided
        effective_session_id = session_id or thread_id or "default_session"
        session = session_manager.get_session(effective_session_id)

        # Update session (increments turn, checks timeout)
        session.update()
        session_context = session.get_context()

        logger.info(
            f"Session context: turn={session_context['conversation_turn']}, "
            f"introduced={session_context['has_introduced']}, "
            f"follow_up={session_context['is_follow_up']}"
        )

        # Create config with tracking
        exec_config = config or {}
        exec_config["track_workflow"] = track_workflow

        initial_state = _create_initial_state(
            input_type="streaming",
            streaming_transcript=streaming_transcript,
            config=exec_config,
        )

        # Inject session context into state (NEW)
        initial_state.update(
            {
                "session_id": effective_session_id,
                "conversation_turn": session_context["conversation_turn"],
                "has_introduced": session_context["has_introduced"],
                "is_follow_up": session_context["is_follow_up"],
                "last_interaction_time": session_context["last_interaction_time"],
            }
        )
        
        # Create new execution logger with task_id
        task_id = initial_state.get("task_id", "unknown")
        cmd_logger = create_new_execution_logger(execution_id=task_id)
        
        # Log streaming command
        cmd_logger.log_command(
            command=streaming_transcript,
            input_type="streaming",
            session_id=effective_session_id,
            metadata={
                "text_length": len(streaming_transcript),
                "conversation_turn": session_context["conversation_turn"],
                "is_follow_up": session_context["is_follow_up"]
            }
        )

        # Execute the graph
        start_time = time.time()

        # Configure execution — thread_id must be inside configurable for the
        # checkpointer to scope state by conversation thread.
        from config.settings import get_settings as _get_settings
        _settings = _get_settings()
        exec_config = {
            "recursion_limit": _settings.graph_recursion_limit,
            "configurable": {
                "thread_id": thread_id or effective_session_id,
                "user_id": initial_state.get("user_id"),
                "task_id": initial_state.get("task_id"),
            },
        }

        logger.debug("Starting graph execution for streaming task")
        result = await app.ainvoke(initial_state, config=exec_config)

        execution_time = time.time() - start_time
        result["execution_time"] = execution_time
        result["end_time"] = time.time()

        # Update session if introduction occurred (NEW)
        if result.get("has_introduced") and not session_context["has_introduced"]:
            session.mark_introduced()
            logger.info(f"Session {effective_session_id} marked as introduced")

        # Ensure spoken_response is set from feedback_message if present
        if result.get("feedback_message") and not result.get("spoken_response"):
            result["spoken_response"] = result["feedback_message"]
        elif not result.get("spoken_response"):
            result["spoken_response"] = "I processed your request."

        logger.info(f"AURA streaming task completed in {execution_time:.2f}s")
        logger.debug(
            f"Final streaming result: status={result.get('status')}, "
            f"intent={result.get('intent', {}).get('action_type') if result.get('intent') else 'none'}"
        )
        
        # Log complete graph execution
        final_status = result.get("status", "unknown")
        cmd_logger.log_graph_execution(
            task_id=initial_state.get("task_id", "unknown"),
            input_data={"input_type": "streaming", "command": streaming_transcript},
            output_data={
                "status": final_status, 
                "transcript": streaming_transcript, 
                "spoken_response": result.get("spoken_response")
            },
            execution_time=execution_time,
            status=final_status,
            metadata={"error": result.get("error_message")} if result.get("error_message") else None
        )
        
        await _finalize_and_upload(cmd_logger, final_status, task_id, result)
        return result

    except Exception as e:
        logger.error(f"Failed to execute AURA streaming task: {e}")
        if cmd_logger:
            await _finalize_and_upload(cmd_logger, "error", task_id if 'task_id' in locals() else "unknown", {})
        return {
            "status": "failed",
            "error_message": f"Task execution failed: {str(e)}",
            "transcript": streaming_transcript,
            "execution_time": time.time()
            - (
                initial_state.get("start_time", time.time())
                if "initial_state" in locals()
                else time.time()
            ),
            "end_time": time.time(),
        }


async def execute_aura_task_from_text(
    app: Any,
    text_input: str,
    config: Dict[str, Any] = None,
    thread_id: str = None,
    track_workflow: bool = False,
) -> Dict[str, Any]:
    """
    Execute AURA task from text input, bypassing STT.

    Args:
        app: Compiled graph application.
        text_input: Text input to process.
        config: Optional execution configuration.
        thread_id: Optional thread ID for state persistence.

    Returns:
        Final task state.
    """
    cmd_logger = None
    try:
        logger.info(f"Executing text task (thread: {thread_id})")

        # Create NEW log file for this execution
        exec_config = config or {}
        should_track = track_workflow or exec_config.get("track_workflow", False)
        exec_config["track_workflow"] = should_track

        initial_state = _create_initial_state(
            input_type="text", transcript=text_input, config=exec_config
        )

        # Inject session/conversation context — same as streaming path so
        # multi-turn awareness (has_introduced, turn counter) works via ADK too.
        from services.conversation_session import get_session_manager
        session_manager = get_session_manager()
        effective_session_id = thread_id or "default_session"
        session = session_manager.get_session(effective_session_id)
        session.update()
        session_context = session.get_context()
        initial_state.update(
            {
                "session_id": effective_session_id,
                "conversation_turn": session_context["conversation_turn"],
                "has_introduced": session_context["has_introduced"],
                "is_follow_up": session_context["is_follow_up"],
                "last_interaction_time": session_context["last_interaction_time"],
            }
        )

        # Create new execution logger with task_id
        task_id = initial_state.get("task_id", "unknown")
        cmd_logger = create_new_execution_logger(execution_id=task_id)

        # Log text command
        cmd_logger.log_command(
            command=text_input,
            input_type="text",
            session_id=effective_session_id,
            metadata={
                "text_length": len(text_input),
                "conversation_turn": session_context["conversation_turn"],
                "config": config,
            }
        )

        # Add any config parameters to state
        if config:
            initial_state.update(config)

        logger.info("Executing graph with initial state")

        # Execute the graph starting from parse_intent instead of stt
        start_time = time.time()

        # Use thread_id for checkpointing if provided
        from config.settings import get_settings as _get_settings
        _rl = _get_settings().graph_recursion_limit
        if thread_id:
            final_state = await app.ainvoke(
                initial_state, config={"configurable": {"thread_id": thread_id}, "recursion_limit": _rl}
            )
        else:
            final_state = await app.ainvoke(initial_state, config={"recursion_limit": _rl})

        end_time = time.time()
        execution_time = end_time - start_time

        # Update final state with execution time
        final_state["execution_time"] = execution_time
        final_state["end_time"] = end_time

        # Extract key information for response
        status = final_state.get("status", "unknown")

        # Generate spoken response if not present
        if not final_state.get("feedback_message") and not final_state.get(
            "spoken_response"
        ):
            final_state["spoken_response"] = final_state.get(
                "feedback_message", "I processed your request."
            )
        elif final_state.get("feedback_message") and not final_state.get(
            "spoken_response"
        ):
            final_state["spoken_response"] = final_state["feedback_message"]

        logger.info(
            f"Task execution completed: status={status}, time={execution_time:.2f}s"
        )

        if final_state.get("error_message"):
            logger.warning(
                f"Task completed with errors: {final_state['error_message']}"
            )
        
        # Log complete graph execution
        cmd_logger.log_graph_execution(
            task_id=initial_state.get("task_id", "unknown"),
            input_data={"input_type": "text", "command": text_input},
            output_data={
                "status": status, 
                "transcript": text_input, 
                "spoken_response": final_state.get("spoken_response")
            },
            execution_time=execution_time,
            status=status,
            metadata={"error": final_state.get("error_message")} if final_state.get("error_message") else None
        )
        
        await _finalize_and_upload(cmd_logger, status, task_id, final_state)
        return final_state

    except Exception as e:
        logger.error(f"Graph execution failed: {e}")
        if cmd_logger:
            await _finalize_and_upload(cmd_logger, "error", task_id if 'task_id' in locals() else "unknown", {})
        return {
            "transcript": text_input,
            "status": "failed",
            "error_message": f"Task execution failed: {str(e)}",
            "spoken_response": "I'm sorry, I encountered an error processing your request.",
            "execution_time": time.time() - (start_time if "start_time" in locals() else time.time()),
            "debug_info": {"error": str(e), "type": type(e).__name__},
        }


async def execute_aura_task(
    app: Any, raw_audio: bytes, config: Dict[str, Any] = None, thread_id: str = None
) -> Dict[str, Any]:
    """
    Execute AURA task from audio input.

    Args:
        app: Compiled graph application.
        raw_audio: Audio data to process.
        config: Optional execution configuration.
        thread_id: Optional thread ID for state persistence.

    Returns:
        Final task state.
    """
    cmd_logger = None
    try:
        logger.info(f"Executing audio task (thread: {thread_id})")

        initial_state = _create_initial_state(
            input_type="audio", raw_audio=raw_audio, config=config
        )
        
        # Create new execution logger with task_id
        task_id = initial_state.get("task_id", "unknown")
        cmd_logger = create_new_execution_logger(execution_id=task_id)
        
        # Log audio command
        cmd_logger.log_command(
            command=f"[Audio Input - {len(raw_audio)} bytes]",
            input_type="audio",
            session_id=initial_state.get("session_id"),
            metadata={"audio_size": len(raw_audio), "config": config}
        )

        # Prepare execution config
        execution_config = config or {}
        if thread_id:
            execution_config["configurable"] = {"thread_id": thread_id}

        # Execute the graph
        logger.info("Executing graph with initial state")
        final_state = None

        async for output in app.astream(initial_state, config=execution_config):
            # Log intermediate states
            for node_name, node_output in output.items():
                logger.debug(f"Node '{node_name}' output: {type(node_output)}")
                final_state = node_output

        if final_state is None:
            raise RuntimeError("Graph execution completed without output")

        # Log execution summary
        status = final_state.get("status", "unknown")
        error_message = final_state.get("error_message")
        execution_time = final_state.get("execution_time", 0.0)

        logger.info(
            f"Task execution completed: status={status}, time={execution_time:.2f}s"
        )

        if error_message:
            logger.warning(f"Task completed with errors: {error_message}")
        
        # Log complete graph execution
        cmd_logger.log_graph_execution(
            task_id=initial_state.get("task_id", "unknown"),
            input_data={"input_type": "audio", "audio_size": len(raw_audio)},
            output_data={
                "status": status, 
                "transcript": final_state.get("transcript"), 
                "spoken_response": final_state.get("spoken_response")
            },
            execution_time=execution_time,
            status=status,
            metadata={"error": error_message} if error_message else None
        )
        
        await _finalize_and_upload(cmd_logger, status, task_id, final_state)
        return final_state

    except Exception as e:
        logger.error(f"Task execution failed: {e}")
        if cmd_logger:
            await _finalize_and_upload(cmd_logger, "error", task_id if 'task_id' in locals() else "unknown", {})
        return {
            "status": "failed",
            "error_message": str(e),
            "spoken_response": "I encountered an error while processing your request.",
            "execution_time": 0.0,
            "retry_count": 0,
        }


def get_graph_info() -> Dict[str, Any]:
    """
    Get information about the graph configuration.

    Returns:
        Dictionary with graph information.
    """
    from config.settings import get_settings

    settings = get_settings()

    return {
        "nodes": [
            "stt",
            "parse_intent",
            "perception",
            "execute",
            "speak",
            "error_handler",
            "decompose_goal",
            "validate_outcome",
            "retry_router",
            "next_subgoal",
            "coordinator",
            "web_search",
        ],
        "entry_point": "stt",
        "edges": {
            "start": ["stt", "parse_intent", "error_handler"],
            "stt": ["parse_intent", "error_handler"],
            "parse_intent": ["perception", "execute", "speak", "error_handler", "coordinator"],
            "perception": ["speak", "error_handler", "coordinator"],
            "execute": ["speak", "error_handler", "perception", "validate_outcome"],
            "validate_outcome": ["next_subgoal", "retry_router", "speak"],
            "retry_router": ["perception", "execute", "speak"],
            "next_subgoal": ["perception"],
            "decompose_goal": ["perception"],
            "coordinator": ["speak"],
            "web_search": ["speak"],
            "error_handler": ["perception", "speak", "END"],
            "speak": ["END"],
        },
        "agents": {
            "commander": {
                "model": f"groq/{settings.default_llm_model}",
                "role": "intent_parsing",
            },
            "coordinator": {
                "model": settings.planning_model,
                "role": "multi_agent_execution",
            },
            "responder": {
                "model": f"groq/{settings.default_llm_model}",
                "role": "feedback_generation",
            },
            "screen_vlm": {
                "model": settings.default_vlm_model,
                "role": "visual_understanding_and_location",
            },
            "validator": {
                "model": f"groq/{settings.default_llm_model}",
                "role": "intent_validation",
            },
        },
        "architecture": "coordinator_parallel",
        "supports_checkpointing": True,
        "supports_streaming": True,
        "version": "3.0.0",
    }


async def run_aura_task(app: Any, initial_state: dict, config: dict = None) -> dict:
    """
    Run the AURA LangGraph with a hard timeout.

    # FIXED: FIX-015 — previously no timeout; stuck device calls blocked forever
    """
    from config.settings import get_settings
    from exceptions_module import AuraTimeoutError

    settings = get_settings()
    timeout = settings.graph_timeout_seconds

    # G13: log which prompt versions are active for this task — aids A/B analysis
    try:
        from prompts import PROMPT_VERSIONS
        from services.command_logger import get_command_logger as _get_cmd_log
        _get_cmd_log().log_agent_decision(
            "PROMPT_VERSIONS",
            {"versions": PROMPT_VERSIONS, "task_id": initial_state.get("task_id", "?")},
            agent_name="Graph",
        )
    except Exception:
        pass

    try:
        result = await asyncio.wait_for(
            app.ainvoke(initial_state, config=config or {}),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        logger.error(f"Graph execution timed out after {timeout}s")
        raise AuraTimeoutError(f"Task timed out after {timeout} seconds")
