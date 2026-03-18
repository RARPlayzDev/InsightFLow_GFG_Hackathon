import { getSessionId } from './session'

const BASE = '/api'

async function apiFetch(path, options = {}) {
  const sid = getSessionId()
  const res = await fetch(BASE + path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Session-ID': sid,
      ...(options.headers || {}),
    },
  })

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || body.message || detail
    } catch {}
    throw new Error(detail)
  }

  return res.json()
}

export async function healthCheck() {
  const res = await fetch(BASE + '/health')
  if (!res.ok) throw new Error(`Health check failed: HTTP ${res.status}`)
  return res.json()
}

export async function preloadDataset() {
  return apiFetch('/preload', { method: 'POST' })
}

export async function uploadCsv(file) {
  const sid = getSessionId()
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(BASE + '/upload-csv', {
    method: 'POST',
    headers: { 'X-Session-ID': sid },
    body: form,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const b = await res.json(); detail = b.detail || detail } catch {}
    throw new Error(detail)
  }
  return res.json()
}

export async function getSchema() {
  return apiFetch('/schema')
}

export async function runQuery(prompt) {
  return apiFetch('/query', {
    method: 'POST',
    body: JSON.stringify({ prompt }),
  })
}

export async function runRefine(message, originalPrompt) {
  return apiFetch('/refine', {
    method: 'POST',
    body: JSON.stringify({ message, original_prompt: originalPrompt }),
  })
}

export async function getHistory() {
  return apiFetch('/history')
}

export async function clearHistory() {
  return apiFetch('/history', { method: 'DELETE' })
}

export async function getOverview() {
  return apiFetch('/overview', { method: 'POST' })
}

export async function sendChatMessage(message, history, context = null) {
  return apiFetch('/chat', {
    method: 'POST',
    body: JSON.stringify({ message, history, context }),
  })
}