export type AgentRole = "host" | "observer" | "pitcher" | "mediator" | "critic";

export type AgentStatus = "idle" | "thinking" | "speaking" | "interrupted" | "listening" | "done" | "streaming" | "error";

export interface PanelState {
  [agentId: string]: {
    status: AgentStatus;
    text: string;
    role: AgentRole;
    name: string;
    avatarUrl?: string;
  };
}

export interface ConversationTurn {
  type: 
    | "question" | "answer" | "reaction" | "interrupt_q" | "interrupt_a" 
    | "host_utterance" | "observer_utterance" | "pitcher_interrupt" 
    | "interrupt_ack" | "interviewer_question" | "persona_response" 
    | "debate_interjection" | "interviewer_invitation" | "pitcher_response"
    | string;
  agent_id?: string;
  agent_name?: string;
  content: string;
}
