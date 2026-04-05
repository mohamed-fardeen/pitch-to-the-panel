from typing import TypedDict, Annotated, List, Optional
import operator
from langgraph.graph import StateGraph, END

class FocusGroupState(TypedDict):
    # Core session data
    session_id: str
    pitch_summary: str
    domain: dict
    difficulty: str
    provider: str
    
    # NEW Agentic Architecture Fields
    action: str  # Decided by controller
    action_input: dict
    action_history: Annotated[List[str], operator.add]
    step_count: int
    max_steps: int
    last_reflection_step: int
    last_persona_used: str
    
    # User Interaction
    input_type: str  # "confirmation | answer | interrupt"
    awaiting_user_input: bool
    pitcher_interrupt: bool
    pitcher_message: str
    
    # Pitch Refinement
    refined_pitch: str
    awaiting_pitch_confirmation: bool
    
    # Memory and Reflection
    memory: dict  # { "claims": [], "risks": [], "strengths": [], "contradictions": [] }
    reflection: dict  # { "missing": [], "confidence": float, "should_continue": bool }
    
    # Conversation history
    conversation: Annotated[List[dict], operator.add]

def build_agentic_graph(
    pitch_refiner_node,
    controller_node,
    persona_node,
    pitcher_node,
    tool_node,
    reflection_node,
    final_node,
    memory_update_node
):
    """
    Build the Controller-driven agentic loop for the Pitch to the Panel system.
    """
    workflow = StateGraph(FocusGroupState)
    
    # Add Nodes
    workflow.add_node("pitch_refiner", pitch_refiner_node)
    workflow.add_node("controller", controller_node)
    workflow.add_node("persona", persona_node)
    workflow.add_node("pitcher", pitcher_node)
    workflow.add_node("tool", tool_node)
    workflow.add_node("reflection", reflection_node)
    workflow.add_node("final", final_node)
    workflow.add_node("memory_update", memory_update_node)
    
    # Entry Point: Pitch refinement always comes first
    workflow.set_entry_point("pitch_refiner")
    
    # Pitch Refinement Loop
    workflow.add_conditional_edges(
        "pitch_refiner",
        lambda x: "wait" if x.get("awaiting_pitch_confirmation") else "continue",
        {
            "wait": "pitch_refiner",  # Loop back if waiting for user
            "continue": "controller"
        }
    )
    
    # Controller uses the router to decide the next step
    workflow.add_conditional_edges(
        "controller",
        action_router,
        {
            "ask_persona": "persona",
            "ask_pitcher": "pitcher",
            "use_tool": "tool",
            "reflect": "reflection",
            "end_session": "final"
        }
    )
    
    # Centralized Memory Update before returning to controller
    workflow.add_edge("persona", "memory_update")
    workflow.add_edge("tool", "memory_update")
    workflow.add_edge("memory_update", "controller")
    
    # These stay direct or handle their own logic
    workflow.add_edge("pitcher", "controller")
    workflow.add_edge("reflection", "controller")
    
    # End node
    workflow.add_edge("final", END)
    
    return workflow.compile()

def action_router(state):
    if state.get("awaiting_user_input"):
        return "controller"

    if state.get("pitcher_interrupt"):
        return "controller"

    if state.get("step_count", 0) >= state.get("max_steps", 20):
        return "end_session"

    action = state.get("action")
    if not action:
        print("[ROUTER WARNING] Missing action")
        return "reflect"

    if (
        state.get("step_count", 0) - state.get("last_reflection_step", 0) >= 3
        and action not in ["reflect", "end_session"]
        and not state.get("awaiting_user_input")
    ):
        return "reflect"

    print(f"[ROUTER] step={state.get('step_count')} → {action}")

    return action
