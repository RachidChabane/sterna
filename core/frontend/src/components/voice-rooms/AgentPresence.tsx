/**
 * Agent color assignment for voice rooms.
 *
 * Assigns each agent a consistent color signature from a shared palette,
 * keyed by its position among the session's agents.
 */

// Premium color palette for agents
const AGENT_COLORS = [
  { r: 56, g: 189, b: 248 },   // sky-400
  { r: 167, g: 139, b: 250 },  // violet-400
  { r: 251, g: 146, b: 60 },   // orange-400
  { r: 244, g: 114, b: 182 },  // pink-400
  { r: 45, g: 212, b: 191 },   // teal-400
  { r: 250, g: 204, b: 21 },   // yellow-400
  { r: 129, g: 140, b: 248 },  // indigo-400
  { r: 74, g: 222, b: 128 },   // green-400
]

// Get a consistent color for an agent based on their ID
export const getAgentColor = (agentId: string, index: number) => {
  // Use index for consistent ordering within a session
  return AGENT_COLORS[index % AGENT_COLORS.length]
}
