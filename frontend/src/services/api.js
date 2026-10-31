/**
 * API service layer for communicating with the FastAPI backend.
 *
 * The base URL is read from the VITE_API_BASE_URL environment variable
 * so it can be changed per-environment without touching source code.
 */

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/**
 * Create a new conversation on the backend.
 * Returns { id, session_id, created_at }.
 */
export async function createConversation() {
  const response = await fetch(`${API_BASE_URL}/api/v1/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });

  if (!response.ok) {
    throw new Error("Failed to create conversation");
  }

  return response.json();
}

/**
 * Send a user message and get the chatbot reply.
 *
 * Uses the context-aware reply endpoint which handles:
 * - FAQ matching
 * - NLP intent/entity extraction
 * - Gemini AI fallback
 * - Conversation history
 *
 * Returns { id, conversation_id, role, content, created_at, answer_source, intent, entities }.
 */
export async function sendMessage(sessionId, message) {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/conversations/${sessionId}/reply`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || `Server error (${response.status})`;
    throw new Error(detail);
  }

  return response.json();
}

/**
 * Quick health check against the backend.
 * Resolves to true if the backend is reachable, false otherwise.
 */
export async function checkHealth() {
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

