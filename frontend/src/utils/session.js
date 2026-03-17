const SESSION_KEY = 'insightflow_session_id'

export function getSessionId() {
  let id = sessionStorage.getItem(SESSION_KEY)
  if (!id) {
    id = 'sess_' + Math.random().toString(36).slice(2, 11) + Date.now().toString(36)
    sessionStorage.setItem(SESSION_KEY, id)
  }
  return id
}

export function clearSession() {
  sessionStorage.removeItem(SESSION_KEY)
}
