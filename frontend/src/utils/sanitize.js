/**
 * HTML Sanitization utilities for XSS prevention.
 * Uses DOMPurify to sanitize untrusted HTML content.
 */

import DOMPurify from "dompurify";

/**
 * Allowed HTML tags for sanitized content.
 * These are safe tags that don't allow script execution.
 */
const ALLOWED_TAGS = [
  "b",
  "i",
  "em",
  "strong",
  "code",
  "mark",
  "span",
  "br",
  "p",
  "div",
  "ul",
  "ol",
  "li",
  "pre",
  "blockquote",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "a",
  "img",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
  "hr",
  "sub",
  "sup",
];

/**
 * Allowed HTML attributes for sanitized content.
 */
const ALLOWED_ATTR = ["class", "style", "href", "src", "alt", "title", "target", "rel"];

/**
 * Configure DOMPurify to prevent XSS attacks while allowing safe HTML.
 */
DOMPurify.setConfig({
  ALLOWED_TAGS,
  ALLOWED_ATTR,
  KEEP_CONTENT: true,
  ALLOW_DATA_ATTR: false,
  ADD_ATTR: ["target"],
  // Force all links to open in new tab with noopener
  FORCE_BODY: false,
});

// Hook to add rel="noopener noreferrer" to all links
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A" && node.hasAttribute("href")) {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
  // Remove javascript: URLs
  if (node.hasAttribute("href")) {
    const href = node.getAttribute("href");
    if (href && href.toLowerCase().startsWith("javascript:")) {
      node.removeAttribute("href");
    }
  }
});

/**
 * Sanitizes HTML content to prevent XSS attacks.
 *
 * @param {string} dirty - The untrusted HTML string to sanitize
 * @returns {string} - The sanitized HTML string
 */
export function sanitizeHtml(dirty) {
  if (!dirty) return "";
  return DOMPurify.sanitize(String(dirty));
}

/**
 * Escapes HTML special characters to prevent injection.
 *
 * @param {string} text - The text to escape
 * @returns {string} - The escaped text
 */
export function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Renders basic markdown-like syntax to HTML and sanitizes the result.
 * Supports: **bold**, *italic*, `code`, and line breaks.
 *
 * @param {string} text - The text with markdown-like syntax
 * @returns {string} - The sanitized HTML string
 */
export function renderMarkdownSafe(text) {
  if (!text) return "";

  // First escape HTML to prevent injection
  let html = escapeHtml(text);

  // Convert markdown-like syntax to HTML
  // Code blocks (must be before inline code)
  html = html.replace(/```([^`]+)```/g, "<pre><code>$1</code></pre>");

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  // Italic
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");

  // Line breaks
  html = html.replace(/\n/g, "<br>");

  // Sanitize the final result
  return sanitizeHtml(html);
}

/**
 * Highlights search terms in text content while maintaining XSS safety.
 *
 * @param {string} text - The text content to highlight
 * @param {string} searchTerm - The search term to highlight
 * @returns {string} - The sanitized HTML with highlighted terms
 */
export function highlightSearchTermSafe(text, searchTerm) {
  if (!text) return "";
  if (!searchTerm || !searchTerm.trim()) return sanitizeHtml(text);

  // Escape both the text and search term
  const escapedText = escapeHtml(text);
  const escapedTerm = escapeHtml(searchTerm.trim());

  // Escape regex special characters in the search term
  const regexSafeTerm = escapedTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  // Create case-insensitive regex
  const regex = new RegExp(`(${regexSafeTerm})`, "gi");

  // Replace matches with highlighted version
  const highlighted = escapedText.replace(regex, '<mark class="search-highlight">$1</mark>');

  // Sanitize the final result
  return sanitizeHtml(highlighted);
}

export default {
  sanitizeHtml,
  escapeHtml,
  renderMarkdownSafe,
  highlightSearchTermSafe,
};
