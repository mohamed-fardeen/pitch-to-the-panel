from typing import TypedDict, Annotated, List
import operator
from langgraph.graph import StateGraph, END

class FocusGroupState(TypedDict):
    # Core session data
    session_id: str
    pitch_summary: str
    domain: dict
    difficulty: str
    provider: str
    
    # Conversation history
    conversation: Annotated[List[dict], operator.add]
    
    # Current turn tracking
    current_question: str
    directed_at: str
    turn_count: int
    
    # Conflict tracking
    last_two_responses: List[dict]
    conflict_detected: bool
    conflict_topic: str
    debater_a: str
    debater_b: str
    
    # Pitcher state
    pitcher_message_pending: bool
    pitcher_message: str
    
    # Control
    should_invite_pitcher: bool
    session_complete: bool
    
    # Flagged claims
    flagged_claims: Annotated[List[dict], operator.add]

def build_focus_group_graph(
    interviewer_node,
    persona_response_node,
    conflict_router_node,
    debate_engine_node,
    invite_pitcher_node,
    hallucination_guard_node,
    check_completion_node
):
    """
    Build the LangGraph state machine for the EchoChamber focus group.
    """
    workflow = StateGraph(FocusGroupState)
    
    # Add nodes
    workflow.add_node("interviewer", interviewer_node)
    workflow.add_node("persona_response", persona_response_node)
    workflow.add_node("conflict_router", conflict_router_node)
    workflow.add_node("debate_engine", debate_engine_node)
    workflow.add_node("invite_pitcher", invite_pitcher_node)
    workflow.add_node("hallucination_guard", hallucination_guard_node)
    workflow.add_node("check_completion", check_completion_node)
    
    # Entry point
    workflow.set_entry_point("interviewer")
    
    # Fixed edges
    workflow.add_edge("interviewer", "persona_response")
    workflow.add_edge("persona_response", "hallucination_guard")
    workflow.add_edge("hallucination_guard", "conflict_router")
    workflow.add_edge("debate_engine", "persona_response")
    workflow.add_edge("invite_pitcher", "interviewer")
    
    # Conditional edges
    workflow.add_conditional_edges(
        "conflict_router",
        route_after_conflict,
        {
            "debate": "debate_engine",
            "continue": "check_completion"
        }
    )
    
    workflow.add_conditional_edges(
        "check_completion",
        route_after_check,
        {
            "invite_pitcher": "invite_pitcher",
            "continue": "interviewer",
            "end": END
        }
    )
    
    return workflow.compile()

def route_after_conflict(state: FocusGroupState):
    if state.get("conflict_detected"):
        return "debate"
    return "continue"

def route_after_check(state: FocusGroupState):
    if state.get("session_complete"):
        return "end"
    if state.get("should_invite_pitcher"):
        return "invite_pitcher"
    return "continue"
