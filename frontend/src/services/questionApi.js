// frontend/src/services/questionApi.js
/**
 * API service for question generation (AllInOne kprim, mc, sc)
 */

const API_BASE = '/api'

/**
 * Get API headers with optional API keys
 */
function getHeaders(apiKeys = {}) {
  const headers = {
    'Content-Type': 'application/json',
  }

  if (apiKeys.anthropic) {
    headers['X-Anthropic-Key'] = apiKeys.anthropic
  }
  if (apiKeys.openai) {
    headers['X-OpenAI-Key'] = apiKeys.openai
  }
  if (apiKeys.perplexity) {
    headers['X-Perplexity-Key'] = apiKeys.perplexity
  }

  return headers
}

/**
 * Generate questions from text using streaming SSE
 *
 * @param {Object} params - Generation parameters
 * @param {string} params.text - Source text for question generation
 * @param {string} params.textContext - Additional context
 * @param {string} params.questionType - 'kprim' | 'mc' | 'sc' | 'mixed'
 * @param {number} params.numQuestions - Target number of questions (null for auto)
 * @param {string} params.model - Model name to use
 * @param {string} params.domain - Domain/category for questions
 * @param {Object} params.apiKeys - API keys { anthropic, openai, perplexity }
 * @param {Function} onProgress - Callback for progress updates
 * @returns {Promise<Array>} - Generated questions
 */
export async function generateQuestionsStream(params, onProgress = null) {
  const {
    text,
    textContext = '',
    questionType = 'mixed',
    numQuestions = null,
    model = null,
    domain = null,
    apiKeys = {},
  } = params

  const response = await fetch(`${API_BASE}/generate-questions-stream`, {
    method: 'POST',
    headers: getHeaders(apiKeys),
    body: JSON.stringify({
      text,
      textContext,
      questionType,
      numQuestions,
      model,
      domain,
    }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.message || err.detail || `HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let questions = []

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Parse SSE events
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''

    for (const eventStr of events) {
      if (!eventStr.trim()) continue

      const lines = eventStr.split('\n')
      let eventType = null
      let eventData = null

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          try {
            eventData = JSON.parse(line.slice(6))
          } catch (e) {
            console.warn('Failed to parse SSE data:', line)
          }
        }
      }

      if (eventType && eventData && onProgress) {
        onProgress({ event: eventType, data: eventData })
      }

      if (eventType === 'questions' && eventData?.questions) {
        questions = eventData.questions
      }

      if (eventType === 'error') {
        throw new Error(eventData?.message || 'Generation failed')
      }
    }
  }

  return questions
}

/**
 * Parse questions from free-form text using AI
 *
 * @param {Object} params - Parse parameters
 * @param {string} params.text - Text containing questions to parse
 * @param {string} params.model - Model name to use
 * @param {Object} params.apiKeys - API keys
 * @param {Function} onProgress - Callback for progress updates
 * @returns {Promise<Array>} - Parsed questions
 */
export async function parseQuestionsStream(params, onProgress = null) {
  const { text, model = null, apiKeys = {} } = params

  const response = await fetch(`${API_BASE}/parse-questions-stream`, {
    method: 'POST',
    headers: getHeaders(apiKeys),
    body: JSON.stringify({
      text,
      model,
    }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.message || err.detail || `HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let questions = []

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    const events = buffer.split('\n\n')
    buffer = events.pop() || ''

    for (const eventStr of events) {
      if (!eventStr.trim()) continue

      const lines = eventStr.split('\n')
      let eventType = null
      let eventData = null

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          try {
            eventData = JSON.parse(line.slice(6))
          } catch (e) {
            console.warn('Failed to parse SSE data:', line)
          }
        }
      }

      if (eventType && eventData && onProgress) {
        onProgress({ event: eventType, data: eventData })
      }

      if (eventType === 'questions' && eventData?.questions) {
        questions = eventData.questions
      }

      if (eventType === 'error') {
        throw new Error(eventData?.message || 'Parsing failed')
      }
    }
  }

  return questions
}

/**
 * Upload questions to Anki using AllInOne note type
 *
 * @param {Object} params - Upload parameters
 * @param {Array} params.questions - Questions to upload
 * @param {string} params.deckName - Target deck name
 * @param {string} params.tags - Comma-separated tags
 * @returns {Promise<Object>} - Upload results
 */
export async function uploadQuestionsToAnki(params) {
  const { questions, deckName = null, tags = '' } = params

  const response = await fetch(`${API_BASE}/upload-questions-to-anki`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      questions,
      deckName,
      tags,
    }),
  })

  const data = await response.json()

  if (!response.ok) {
    throw new Error(data.message || data.error || `HTTP ${response.status}`)
  }

  return data
}

/**
 * Check if AllInOne note type is available in Anki
 *
 * @returns {Promise<Object>} - { hasModel, modelName, fields, installUrl }
 */
export async function checkAllInOneModel() {
  const response = await fetch(`${API_BASE}/check-allinone-model`)
  const data = await response.json()

  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`)
  }

  return data
}

/**
 * Get default prompts for question generation
 *
 * @returns {Promise<Object>} - Prompts configuration
 */
export async function getQuestionPrompts() {
  const response = await fetch(`${API_BASE}/question-prompts`)
  const data = await response.json()

  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`)
  }

  return data
}

export default {
  generateQuestionsStream,
  parseQuestionsStream,
  uploadQuestionsToAnki,
  checkAllInOneModel,
  getQuestionPrompts,
}
