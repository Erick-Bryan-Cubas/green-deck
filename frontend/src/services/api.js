/**
 * Client API for Flash Card Generator
 *
 * Handles client-side API key management and server API requests
 */

// Local storage key for API keys
const API_KEY_STORAGE_KEY = "flashcard_generator_api_keys";

/**
 * Retrieves stored API keys from local storage
 * @returns {Object} Object containing API keys
 */
function getStoredApiKeys() {
  try {
    const storedData = localStorage.getItem(API_KEY_STORAGE_KEY);
    if (storedData) {
      return JSON.parse(storedData);
    }
  } catch (error) {
    console.error("Error reading stored API keys:", error);
  }
  return { anthropicApiKey: null, openaiApiKey: null, perplexityApiKey: null };
}

/**
 * Stores API keys in local storage
 * @param {string} anthropicApiKey - Claude API key
 * @param {string} openaiApiKey - OpenAI API key
 * @param {string} perplexityApiKey - Perplexity API key
 * @param {boolean} storeLocally - Whether to store keys locally
 * @returns {boolean} Success status
 */
function storeApiKeys(anthropicApiKey, openaiApiKey, perplexityApiKey, storeLocally = true) {
  if (storeLocally) {
    try {
      localStorage.setItem(
        API_KEY_STORAGE_KEY,
        JSON.stringify({
          anthropicApiKey,
          openaiApiKey,
          perplexityApiKey,
        })
      );
      return true;
    } catch (error) {
      console.error("Error storing API keys:", error);
      return false;
    }
  } else {
    try {
      localStorage.removeItem(API_KEY_STORAGE_KEY);
    } catch (error) {
      console.error("Error clearing API keys:", error);
    }
    return true;
  }
}

/**
 * Validates format of Anthropic API key
 * @param {string} key - API key to validate
 * @returns {boolean} Whether key appears valid
 */
function validateAnthropicApiKey(key) {
  return key && key.startsWith("sk-ant-") && key.length > 20;
}

/**
 * Checks if API keys are configured
 * @returns {boolean} Whether keys are available
 */
function hasApiKeys() {
  const keys = getStoredApiKeys();
  return !!keys.anthropicApiKey;
}

/**
 * Checks if ANY API key is configured (Anthropic, OpenAI or Perplexity)
 * Used for fallback logic to Ollama
 * @returns {boolean} Whether any key is available
 */
function hasAnyApiKey() {
  const keys = getStoredApiKeys();
  return !!(keys.anthropicApiKey || keys.openaiApiKey || keys.perplexityApiKey);
}

/**
 * Fetches detailed Ollama information including models, running models, and GPU/VRAM usage
 * @returns {Promise<Object>} Ollama info object
 */
async function fetchOllamaInfo() {
  try {
    const response = await fetch("/api/ollama-info");
    if (!response.ok) {
      return {
        connected: false,
        models: [],
        running_models: [],
        gpu_info: { using_gpu: false, vram_used_mb: 0 }
      };
    }
    return await response.json();
  } catch (error) {
    console.error("Error fetching Ollama info:", error);
    return {
      connected: false,
      models: [],
      running_models: [],
      gpu_info: { using_gpu: false, vram_used_mb: 0 }
    };
  }
}

/**
 * Helper function to truncate text to a reasonable size
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Maximum length
 * @returns {string} Truncated text
 */
function truncateText(text, maxLength = 8000) {
  if (!text || text.length <= maxLength) return text;
  return text.substring(0, maxLength) + "... [truncated]";
}

/**
 * Creates HTTP headers with API keys for secure transmission.
 * API keys are sent via headers instead of request body to avoid logging exposure.
 * @param {Object} keys - Object containing API keys
 * @returns {Object} Headers object with Content-Type and API key headers
 */
function createApiHeaders(keys = null) {
  const headers = { "Content-Type": "application/json" };
  const apiKeys = keys || getStoredApiKeys();

  if (apiKeys.anthropicApiKey) {
    headers["X-Anthropic-Key"] = apiKeys.anthropicApiKey;
  }
  if (apiKeys.openaiApiKey) {
    headers["X-OpenAI-Key"] = apiKeys.openaiApiKey;
  }
  if (apiKeys.perplexityApiKey) {
    headers["X-Perplexity-Key"] = apiKeys.perplexityApiKey;
  }

  return headers;
}

/**
 * Normaliza o campo de referência do card, aceitando algumas variações.
 * (ex: src, SRC, fonte, ref)
 */
function pickSrcField(card) {
  if (!card || typeof card !== "object") return "";
  return (
    card.src ||
    card.SRC ||
    card.fonte ||
    card.FONTE ||
    card.ref ||
    card.REF ||
    ""
  );
}

/**
 * Parses AI response to extract structured card data
 * @param {Object} responseData - Raw response from AI API
 * @returns {Array} Array of card objects
 */
function parseClaudeResponse(responseData) {
  let responseText = "";

  // Extract text content from response
  if (responseData.content && Array.isArray(responseData.content)) {
    for (const item of responseData.content) {
      if (item.type === "text") {
        responseText += item.text;
      }
    }
  } else if (responseData.content && responseData.content[0] && responseData.content[0].text) {
    responseText = responseData.content[0].text;
  } else {
    console.warn("Unexpected response format from AI API");
    responseText = JSON.stringify(responseData);
  }

  // Try to parse as JSON
  try {
    // First, extract JSON if it's embedded in other text
    const jsonMatch = responseText.match(/(\[\s*\{.*\}\s*\])/s);
    const jsonText = jsonMatch ? jsonMatch[1] : responseText;

    const parsedCards = JSON.parse(jsonText);
    console.log("Successfully parsed JSON cards:", parsedCards);

    if (Array.isArray(parsedCards) && parsedCards.length > 0) {
      const validCards = parsedCards
        .filter((card) => card.front && card.back)
        .map((card) => ({
          front: card.front,
          back: card.back,
          deck: card.deck || "General",
          // ✅ NOVO: preservar referência ao trecho (quando existir)
          src: pickSrcField(card),
        }));

      if (validCards.length > 0) {
        console.log("Returning valid JSON cards:", validCards);
        return validCards;
      }
    }
    console.warn("Parsed JSON did not contain valid cards");
  } catch (error) {
    console.warn("Failed to parse response as JSON:", error);

    // Try searching for JSON inside the text (sometimes AI wraps JSON in backticks or other text)
    try {
      const jsonRegex = /```(?:json)?\s*(\[\s*\{[\s\S]*?\}\s*\])\s*```/;
      const match = responseText.match(jsonRegex);
      if (match && match[1]) {
        const extractedJson = match[1];
        const parsedCards = JSON.parse(extractedJson);

        if (Array.isArray(parsedCards) && parsedCards.length > 0) {
          const validCards = parsedCards
            .filter((card) => card.front && card.back)
            .map((card) => ({
              front: card.front,
              back: card.back,
              deck: card.deck || "General",
              // ✅ NOVO: preservar referência ao trecho (quando existir)
              src: pickSrcField(card),
            }));

          if (validCards.length > 0) {
            console.log(
              "Returning valid JSON cards (extracted from code block):",
              validCards
            );
            return validCards;
          }
        }
      }
    } catch (innerError) {
      console.warn("Failed to extract JSON from code blocks:", innerError);
    }
  }

  // Fallback: If JSON parsing fails, create a basic fallback card
  console.warn("Could not parse any cards from AI response, using fallback");
  return [
    {
      front: "What are the key concepts from this text?",
      back:
        responseText.length > 300
          ? responseText.substring(0, 300) + "..."
          : responseText,
      deck: "General",
      // ✅ NOVO: manter consistência do shape do card
      src: "",
    },
  ];
}

/**
 * Analyzes text to extract key context information
 * Returns a concise summary of the document's main points and author
 *
 * @param {string} text - The full text to analyze
 * @param {string} analysisModel - Model to use for embeddings/analysis
 * @param {(percent: number)=>void} onProgress - Progress callback
 * @returns {Promise<string>} - Context summary
 */
async function analyzeText(text, analysisModel = null, onProgress = null) {
  try {
    const response = await fetch("/api/analyze-text-stream", {
      method: "POST",
      headers: createApiHeaders(),
      body: JSON.stringify({
        text: truncateText(text, 10000),
        analysisModel: analysisModel,
      }),
    });

    if (!response.ok) throw new Error("API Error");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result = null;
    let analysisId = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let parts = buffer.split("\n\n");
      buffer = parts.pop();

      for (const part of parts) {
        const lines = part.split("\n");
        let event = "message";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("event:")) event = line.replace("event:", "").trim();
          else if (line.startsWith("data:")) data += line.replace("data:", "").trim();
        }

        try {
          const parsed = data ? JSON.parse(data) : null;
          if (event === "error" && parsed) {
            throw new Error(parsed.error || "Analysis failed");
          } else if (event === "progress" && onProgress) {
            onProgress(parsed.percent || 0);
            if (parsed.analysis_id) analysisId = parsed.analysis_id;
          } else if (event === "result") {
            result = parsed;
            if (parsed.analysis_id) analysisId = parsed.analysis_id;
          }
        } catch (e) {
          if (event === "error") {
            throw e;
          }
          // Ignore JSON parse errors for intermediate events
        }
      }
    }

    if (result && result.content) {
      let contextSummary = "";
      for (const item of result.content) {
        if (item.type === "text") contextSummary += item.text;
      }
      return { summary: contextSummary, analysisId };
    }

    throw new Error("No result from analysis");
  } catch (error) {
    console.error("Error analyzing text:", error);
    throw error;
  }
}

/**
 * Segments text into topic-based chunks for automatic highlighting
 * Returns positions for each segment with topic classification
 *
 * @param {string} text - The text to segment
 * @param {string} analysisModel - Model to use for segmentation
 * @param {(event: {stage:string, data:object})=>void} onProgress - Progress callback
 * @returns {Promise<{segments: Array, topics: Array, analysis_id: string}>}
 */
async function segmentTopics(text, analysisModel = null, onProgress = null) {
  try {
    const response = await fetch("/api/segment-topics", {
      method: "POST",
      headers: createApiHeaders(),
      body: JSON.stringify({
        text: truncateText(text, 15000),
        analysisModel: analysisModel,
      }),
    });

    if (!response.ok) throw new Error("API Error");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let parts = buffer.split("\n\n");
      buffer = parts.pop();

      for (const part of parts) {
        const lines = part.split("\n");
        let event = "message";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("event:")) event = line.replace("event:", "").trim();
          else if (line.startsWith("data:")) data += line.replace("data:", "").trim();
        }

        try {
          const parsed = data ? JSON.parse(data) : null;
          if (event === "error" && parsed) {
            throw new Error(parsed.error || "Segmentation failed");
          } else if (event === "progress" && onProgress) {
            onProgress({ stage: parsed.stage, data: parsed });
          } else if (event === "result") {
            result = parsed;
          }
        } catch (e) {
          if (event === "error") {
            throw e;
          }
          // Ignore JSON parse errors for intermediate events
        }
      }
    }

    if (result && result.success) {
      return {
        segments: result.segments || [],
        topics: result.topics || [],
        text_length: result.text_length || 0,
        analysis_id: result.analysis_id,
      };
    }

    throw new Error("No result from segmentation");
  } catch (error) {
    console.error("Error segmenting topics:", error);
    throw error;
  }
}

/**
 * Calls AI API to generate flashcards from text
 * Uses server-side proxy with user-provided API key
 *
 * @param {string} text - The highlighted text selection to create cards from
 * @param {string} deckOptions - Comma-separated list of available deck options
 * @param {string} textContext - Optional context summary for the document
 * @returns {Promise<Array>} - Array of card objects with front, back, and deck properties
 */
async function generateCards(text, deckOptions = "", textContext = "") {
  try {
    // If no Anthropic API key is provided, the server will attempt to use a local Ollama instance

    // Call the server endpoint with timeout control
    let response;
    try {
      // Create an AbortController to handle timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 second client-side timeout

      response = await fetch("/api/generate-cards", {
        method: "POST",
        headers: createApiHeaders(),
        body: JSON.stringify({
          text: truncateText(text),
          textContext,
          deckOptions,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
    } catch (fetchError) {
      if (fetchError.name === "AbortError") {
        throw new Error(
          `Request timed out. Please select a smaller portion of text and try again.`
        );
      }
      throw new Error(
        `Network error: Could not connect to the API server. ${fetchError.message}`
      );
    }

    // Read the response once as text
    const responseText = await response.text();

    if (!response.ok) {
      try {
        // Try to parse as JSON
        const errorData = JSON.parse(responseText);
        throw new Error(`API Error: ${errorData.error || "Unknown server error"}`);
      } catch (e) {
        // If parsing fails, use the text directly
        throw new Error(`API Error: ${responseText.substring(0, 100)}`);
      }
    }

    // Parse the already-read text as JSON
    const responseData = JSON.parse(responseText);
    return parseClaudeResponse(responseData);
  } catch (error) {
    console.error("Error calling API:", error);

    // Provide more user-friendly error messages
    if (error.message.includes("No API key provided")) {
      throw new Error("Please add your API key in the settings (gear icon).");
    } else if (
      error.message.includes("Network error") ||
      error.message.includes("Failed to fetch")
    ) {
      throw new Error(
        "Connection to server failed. Please check your internet connection and try again."
      );
    } else if (error.message.includes("API Error") && error.message.length > 200) {
      // Truncate very long error messages
      throw new Error(error.message.substring(0, 200) + "...");
    }

    throw error;
  }
}

/**
 * Gera flashcards usando streaming SSE
 * @param {string} text - Texto fonte para gerar cards
 * @param {string} deckOptions - Deck de destino
 * @param {string} textContext - Contexto adicional
 * @param {string} cardType - Tipo de card (basic, cloze, both)
 * @param {string} model - Modelo LLM para geracao
 * @param {(event: {stage:string, data:object})=>void} onProgress - Callback de progresso
 * @param {string} analysisId - ID da analise
 * @param {string} validationModel - Modelo para validacao
 * @param {string} analysisModel - Modelo para analise
 * @param {Object} customPrompts - Prompts personalizados (opcional)
 * @param {number|null} numCards - Quantidade desejada de cards (opcional)
 * @returns {Promise<Array>} cards
 */
async function generateCardsWithStream(
  text,
  deckOptions = "",
  textContext = "",
  cardType = "basic",
  model = "qwen-flashcard",
  onProgress = null,
  analysisId = null,
  validationModel = null,
  analysisModel = null,
  customPrompts = null,
  numCards = null,
  isExamMode = false
) {
  // Monta o body com campos opcionais de prompts customizados
  // Note: API keys are now sent via headers for security
  const requestBody = {
    text: truncateText(text),
    textContext,
    deckOptions,
    cardType,
    model,
    validationModel: validationModel || model,
    analysisModel: analysisModel || model,
    analysisId,
  };

  // Adiciona quantidade de cards se especificada
  if (numCards && numCards > 0) {
    requestBody.numCards = numCards;
  }

  // Adiciona modo de simulado/prova se ativo
  if (isExamMode) {
    requestBody.isExamMode = true;
  }

  // Adiciona prompts customizados se fornecidos
  if (customPrompts) {
    if (customPrompts.systemPrompt) {
      requestBody.customSystemPrompt = customPrompts.systemPrompt;
    }
    if (customPrompts.generationPrompt) {
      requestBody.customGenerationPrompt = customPrompts.generationPrompt;
    }
    if (customPrompts.guidelines) {
      requestBody.customGuidelines = customPrompts.guidelines;
    }
  }

  let response;
  try {
    response = await fetch("/api/generate-cards-stream", {
      method: "POST",
      headers: createApiHeaders(),
      body: JSON.stringify(requestBody),
    });
  } catch (err) {
    throw new Error("Network error: " + err.message);
  }

  if (!response.ok) {
    const txt = await response.text();
    throw new Error("API Error: " + txt.substring(0, 200));
  }

  // Read streaming body and parse SSE-style events
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let finalResult = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Process complete event blocks separated by double newline
    let parts = buffer.split("\n\n");
    buffer = parts.pop(); // keep incomplete tail

    for (const part of parts) {
      const lines = part.split("\n");
      let event = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.replace("event:", "").trim();
        else if (line.startsWith("data:")) data += line.replace("data:", "").trim();
      }

      try {
        const parsed = data ? JSON.parse(data) : null;
        if (onProgress) onProgress({ stage: event, data: parsed });

        if (event === "result" && parsed) {
          finalResult = parsed;
        }
      } catch (e) {
        // ignore JSON parse errors for intermediate events
        if (onProgress) onProgress({ stage: event, data: { raw: data } });
      }
    }
  }

  // If finalResult contains cards, preserve src too
  if (finalResult && finalResult.success && Array.isArray(finalResult.cards)) {
    return finalResult.cards.map((c) => ({
      front: c.front || "",
      back: c.back || "",
      deck: c.deck || "General",
      // ✅ NOVO: preservar referência do trecho no streaming também
      src: c.src || "",
    }));
  }

  // Fallback: try to parse any textual payload
  if (finalResult && finalResult.cards && typeof finalResult.cards === "string") {
    try {
      const parsed = JSON.parse(finalResult.cards);
      if (Array.isArray(parsed)) return parsed;
    } catch (e) {}
  }

  throw new Error("No cards returned from API");
}

// =============================================================================
// Document Extraction API
// =============================================================================

/**
 * Checks if document extraction service is available
 * @returns {Promise<Object>} Status object with available flag and supported formats
 */
async function getDocumentExtractionStatus() {
  try {
    const response = await fetch("/api/documents/status");
    if (!response.ok) {
      return { available: false, supported_formats: [], max_file_size_mb: 0 };
    }
    return await response.json();
  } catch (error) {
    console.error("Error checking document extraction status:", error);
    return { available: false, supported_formats: [], max_file_size_mb: 0 };
  }
}

/**
 * Extracts text from a PDF document
 * @param {File} file - PDF file to extract text from
 * @param {Object} options - Extraction options
 * @param {string} options.quality - Extraction quality: 'raw', 'cleaned', or 'llm'
 * @param {number} options.chunkSize - Optional chunk size in words
 * @param {string} options.pdfExtractor - PDF extractor: 'docling' or 'pdfplumber'
 * @param {(progress: number) => void} onProgress - Progress callback (0-100)
 * @returns {Promise<Object>} Extraction result with text, pages, word_count, etc.
 */
async function extractDocumentText(file, options = {}, onProgress = null) {
  const { quality = "cleaned", chunkSize = null, pdfExtractor = "docling" } = options;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("quality", quality);
  formData.append("pdf_extractor", pdfExtractor);
  if (chunkSize) {
    formData.append("chunk_size", chunkSize.toString());
  }

  try {
    const response = await fetch("/api/documents/extract", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      try {
        const errorJson = JSON.parse(errorText);
        throw new Error(errorJson.detail || "Extraction failed");
      } catch {
        throw new Error(errorText.substring(0, 200));
      }
    }

    const result = await response.json();
    
    if (!result.success) {
      throw new Error(result.error || "Extraction failed");
    }

    return result;
  } catch (error) {
    console.error("Error extracting document:", error);
    throw error;
  }
}

/**
 * Extracts text from PDF and returns a preview
 * @param {File} file - PDF file
 * @param {number} maxPreviewChars - Maximum characters in preview
 * @returns {Promise<Object>} Preview result with truncated text and stats
 */
async function extractDocumentPreview(file, maxPreviewChars = 2000) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("max_preview_chars", maxPreviewChars.toString());

  try {
    const response = await fetch("/api/documents/extract-and-preview", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      try {
        const errorJson = JSON.parse(errorText);
        throw new Error(errorJson.detail || "Preview extraction failed");
      } catch {
        throw new Error(errorText.substring(0, 200));
      }
    }

    return await response.json();
  } catch (error) {
    console.error("Error extracting document preview:", error);
    throw error;
  }
}

/**
 * Gets preview of each page in a document
 * @param {File} file - Document file (PDF, DOCX, PPTX, etc.)
 * @returns {Promise<Object>} Preview result with page info
 */
async function getDocumentPagesPreview(file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch("/api/documents/preview-pages", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      try {
        const errorJson = JSON.parse(errorText);
        throw new Error(errorJson.detail || "Preview failed");
      } catch {
        throw new Error(errorText.substring(0, 200));
      }
    }

    return await response.json();
  } catch (error) {
    console.error("Error getting document pages preview:", error);
    throw error;
  }
}

// Alias for backward compatibility
const getPdfPagesPreview = getDocumentPagesPreview;

/**
 * Extracts text from selected pages of a document
 * @param {File} file - Document file (PDF, DOCX, PPTX, etc.)
 * @param {number[]} pageNumbers - Array of page numbers (1-indexed)
 * @param {string} quality - Extraction quality: 'raw', 'cleaned', or 'llm'
 * @param {string} pdfExtractor - PDF extractor: 'docling' or 'pdfplumber'
 * @returns {Promise<Object>} Extraction result with text from selected pages
 */
async function extractSelectedPages(file, pageNumbers, quality = "cleaned", pdfExtractor = "docling") {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("page_numbers", pageNumbers.join(","));
  formData.append("quality", quality);
  formData.append("pdf_extractor", pdfExtractor);

  try {
    const response = await fetch("/api/documents/extract-pages", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      try {
        const errorJson = JSON.parse(errorText);
        throw new Error(errorJson.detail || "Extraction failed");
      } catch {
        throw new Error(errorText.substring(0, 200));
      }
    }

    const result = await response.json();
    
    if (!result.success) {
      throw new Error(result.error || "Extraction failed");
    }

    return result;
  } catch (error) {
    console.error("Error extracting selected pages:", error);
    throw error;
  }
}

/**
 * Busca os prompts padrao do servidor para exibicao/edicao no frontend
 * @returns {Promise<Object>} Objeto com prompts organizados por categoria
 */
async function getDefaultPrompts() {
  try {
    const response = await fetch("/api/prompts/defaults");
    if (!response.ok) {
      throw new Error("Failed to fetch default prompts");
    }
    return await response.json();
  } catch (error) {
    console.error("Error fetching default prompts:", error);
    throw error;
  }
}

/**
 * Reescreve um card usando LLM
 * @param {Object} card - Card a ser reescrito {front, back}
 * @param {string} action - Acao: "densify" | "split_cloze" | "simplify"
 * @param {string} model - Modelo LLM para reescrita
 * @returns {Promise<Object>} Card reescrito {success, front, back, action}
 */
async function rewriteCard(card, action, model = null) {
  try {
    const response = await fetch("/api/rewrite-card", {
      method: "POST",
      headers: createApiHeaders(),
      body: JSON.stringify({
        front: card.front || "",
        back: card.back || "",
        action: action,
        model: model,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error("API Error: " + errorText.substring(0, 200));
    }

    return await response.json();
  } catch (error) {
    console.error("Error rewriting card:", error);
    throw error;
  }
}

export {
  generateCards,
  generateCardsWithStream,
  analyzeText,
  segmentTopics,
  getStoredApiKeys,
  storeApiKeys,
  validateAnthropicApiKey,
  hasApiKeys,
  hasAnyApiKey,
  fetchOllamaInfo,
  getDocumentExtractionStatus,
  extractDocumentText,
  extractDocumentPreview,
  getDocumentPagesPreview,
  getPdfPagesPreview, // Alias for backward compatibility
  extractSelectedPages,
  getDefaultPrompts,
  rewriteCard,
};
