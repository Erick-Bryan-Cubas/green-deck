// Import Claude API functions
import { 
    generateCardsWithClaude, 
    generateCardsWithStream,
    analyzeTextWithClaude,
    getStoredApiKeys,
    storeApiKeys,
    validateAnthropicApiKey,
    hasApiKeys
} from './claude-api.js';

// Import Progress Bar
import { ProgressBar } from './progress-bar.js';

// Quill.js is loaded globally from CDN

document.addEventListener('DOMContentLoaded', () => {
    // API Key Management
    const apiKeyModal = document.getElementById('apiKeyModal');
    const settingsButton = document.getElementById('settingsButton');
    const anthropicApiKeyInput = document.getElementById('anthropicApiKey');
    const mochiApiKeyInput = document.getElementById('mochiApiKey');
    const storeLocallyCheckbox = document.getElementById('storeLocallyCheckbox');
    const apiKeySaveButton = document.getElementById('apiKeySave');
    const apiKeyCancelButton = document.getElementById('apiKeyCancel');
    const anthropicApiKeyError = document.getElementById('anthropicApiKeyError');
    
    // Dropdown Menu
    const menuButton = document.getElementById('menuButton');
    const dropdownMenu = document.getElementById('dropdown-menu');
    
    // Toggle dropdown menu when menu button is clicked
    menuButton.addEventListener('click', () => {
        const expanded = menuButton.getAttribute('aria-expanded') === 'true';
        
        if (expanded) {
            // Close dropdown
            dropdownMenu.classList.remove('show');
            menuButton.setAttribute('aria-expanded', 'false');
        } else {
            // Open dropdown
            dropdownMenu.classList.add('show');
            menuButton.setAttribute('aria-expanded', 'true');
        }
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', (event) => {
        if (!menuButton.contains(event.target) && !dropdownMenu.contains(event.target)) {
            dropdownMenu.classList.remove('show');
            menuButton.setAttribute('aria-expanded', 'false');
        }
    });
    
    // Check for stored API keys on startup
    const storedKeys = getStoredApiKeys();
    if (storedKeys.anthropicApiKey) {
        // Pre-fill the form with stored keys (masked)
        anthropicApiKeyInput.value = storedKeys.anthropicApiKey;
        if (storedKeys.mochiApiKey) {
            mochiApiKeyInput.value = storedKeys.mochiApiKey;
            // Fetch decks right away if we have a Mochi API key
            fetchDecks()
                .catch(error => console.error('Failed to load Mochi decks on startup:', error));
        }
    } else {
        // No Anthropic API key stored — do not force modal. Server may use local Ollama fallback.
    }
    
    // Settings button opens the API key modal
    settingsButton.addEventListener('click', showApiKeyModal);
    
    // Save button in API key modal
    apiKeySaveButton.addEventListener('click', async () => {
        const anthropicKey = anthropicApiKeyInput.value.trim();
        const mochiKey = mochiApiKeyInput.value.trim();
        const storeLocally = storeLocallyCheckbox.checked;
        
        // If an Anthropic key was provided, validate it; otherwise allow empty to use Ollama fallback
        if (anthropicKey && !validateAnthropicApiKey(anthropicKey)) {
            anthropicApiKeyError.textContent = 'Required: Enter a valid Claude API key (starts with sk-ant-)';
            anthropicApiKeyInput.focus();
            return;
        }
        
        // Store the API keys
        const saveSuccess = storeApiKeys(anthropicKey, mochiKey, storeLocally);
        
        if (saveSuccess) {
            // Close the modal
            apiKeyModal.style.display = 'none';
            
            // Update UI based on available keys
            updateUiForApiKeys();
            
            // Fetch decks if Mochi API key is provided
            if (mochiKey) {
                try {
                    await fetchDecks();
                    // Mochi decks successfully fetched
                } catch (error) {
                    console.error('Failed to fetch Mochi decks:', error);
                    showNotification('Failed to connect to Mochi API', 'error');
                }
            }
            
            // Show success notification
            showNotification('API keys saved successfully', 'success');
        } else {
            // Show error notification
            showNotification('Failed to save API keys', 'error');
        }
    });
    
    // Cancel button in API key modal
    apiKeyCancelButton.addEventListener('click', () => {
        // Close the modal; it's optional to provide an Anthropic API key (server will fallback to Ollama)
        apiKeyModal.style.display = 'none';
    });
    
    function showApiKeyModal() {
        // Reset error message
        anthropicApiKeyError.textContent = '';
        
        // Fill in the form with stored values if available
        const storedKeys = getStoredApiKeys();
        if (storedKeys.anthropicApiKey) {
            anthropicApiKeyInput.value = storedKeys.anthropicApiKey;
        }
        if (storedKeys.mochiApiKey) {
            mochiApiKeyInput.value = storedKeys.mochiApiKey;
        }
        
        // Show the modal
        apiKeyModal.style.display = 'flex';
    }
    
    function updateUiForApiKeys() {
        const keys = getStoredApiKeys();
        
        // Update export button text based on whether we have a Mochi API key
        const exportButton = document.getElementById('exportButton');
        if (keys.mochiApiKey) {
            exportButton.textContent = 'Export to Mochi';
        } else {
            exportButton.textContent = 'Export as Markdown';
        }
    }
    
    // Call this on startup to set up the UI correctly
    updateUiForApiKeys();
    // DOM Elements
    const textInput = document.getElementById('textInput');
    const generateButton = document.getElementById('generateButton');
    const cardsContainer = document.getElementById('cardsContainer');
    const exportButton = document.getElementById('exportButton');
    const clearCardsButton = document.getElementById('clearCardsButton');
    const splitterHandle = document.getElementById('splitterHandle');
    const editorPanel = document.getElementById('editorPanel');
    const outputPanel = document.getElementById('outputPanel');
    
    // App State
    const state = {
        cards: [],
        selectedText: '',
        currentDeck: null,
        decks: {},
        documentContext: '',
        isAnalyzing: false,
        fromPaste: false,
        editor: null
    };
    
    // Timer
    const processingTimer = document.getElementById('processingTimer');
    const timerText = document.getElementById('timerText');
    const timerValue = document.getElementById('timerValue');
    let timerInterval = null;
    let timerSeconds = 0;
    
    function startTimer(text) {
        timerSeconds = 0;
        timerText.textContent = text;
        timerValue.textContent = '0s';
        processingTimer.style.display = 'inline-flex';
        
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            timerSeconds++;
            timerValue.textContent = `${timerSeconds}s`;
        }, 1000);
    }
    
    function stopTimer() {
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
        }
        processingTimer.style.display = 'none';
    }
    
    // Logs Panel
    const logsPanel = document.getElementById('logsPanel');
    const logsContent = document.getElementById('logsContent');
    const toggleLogsButton = document.getElementById('toggleLogsButton');
    const closeLogsButton = document.getElementById('closeLogsButton');
    const clearLogsButton = document.getElementById('clearLogsButton');
    
    function addLog(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${type}`;
        logEntry.innerHTML = `<span class="log-timestamp">[${timestamp}]</span>${message}`;
        logsContent.appendChild(logEntry);
        logsContent.scrollTop = logsContent.scrollHeight;
    }
    
    toggleLogsButton.addEventListener('click', () => {
        logsPanel.style.display = logsPanel.style.display === 'none' ? 'flex' : 'none';
    });
    
    closeLogsButton.addEventListener('click', () => {
        logsPanel.style.display = 'none';
    });
    
    clearLogsButton.addEventListener('click', () => {
        logsContent.innerHTML = '';
        addLog('Logs cleared', 'info');
    });
    
    // Initialize Quill Editor
    function initQuillEditor() {
        try {
            // Configure Quill with the modules and formats we want
            const toolbarOptions = [
                [{ 'header': [1, 2, 3, false] }],
                ['bold', 'italic'],
                [{ 'list': 'ordered'}, { 'list': 'bullet' }],
                [{ 'background': [] }]
            ];
            
            // Create a new Quill editor instance
            state.editor = new Quill('#textInput', {
                modules: {
                    toolbar: toolbarOptions
                },
                placeholder: 'Paste or type your text here, then highlight sections to generate cards...',
                theme: 'snow'
            });
            
            // Custom background color picker
            const backgroundButton = document.querySelector('.ql-background');
            if (backgroundButton) {
                backgroundButton.innerHTML = '<span style="font-size: 16px;">🖍️</span>';
                
                const colors = [
                    { color: '#fef08a', label: 'Amarelo' },
                    { color: '#bbf7d0', label: 'Verde' },
                    { color: '#bfdbfe', label: 'Azul' },
                    { color: '#fbcfe8', label: 'Rosa' },
                    { color: '#ddd6fe', label: 'Roxo' },
                    { color: '#fed7aa', label: 'Laranja' },
                    { color: 'transparent', label: 'Remover' }
                ];
                
                let savedRange = null;
                
                backgroundButton.addEventListener('mousedown', (e) => {
                    savedRange = state.editor.getSelection();
                });
                
                backgroundButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const existingPicker = document.querySelector('.custom-color-picker');
                    if (existingPicker) {
                        existingPicker.remove();
                        return;
                    }
                    
                    const picker = document.createElement('div');
                    picker.className = 'custom-color-picker';
                    picker.style.cssText = `
                        position: absolute;
                        background: var(--gray-800);
                        border: 1px solid var(--gray-700);
                        border-radius: 8px;
                        padding: 8px;
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
                        z-index: 9999;
                        display: grid;
                        grid-template-columns: repeat(3, 1fr);
                        gap: 6px;
                        width: 140px;
                    `;
                    
                    const rect = backgroundButton.getBoundingClientRect();
                    picker.style.left = rect.left + 'px';
                    picker.style.top = (rect.bottom + 5) + 'px';
                    
                    colors.forEach(({ color, label }) => {
                        const btn = document.createElement('button');
                        btn.style.cssText = `
                            width: 36px;
                            height: 36px;
                            border-radius: 4px;
                            border: 2px solid var(--gray-700);
                            background-color: ${color};
                            cursor: pointer;
                            transition: all 0.15s ease;
                            ${color === 'transparent' ? 'background-image: linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc), linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc); background-size: 8px 8px; background-position: 0 0, 4px 4px;' : ''}
                        `;
                        btn.title = label;
                        
                        btn.addEventListener('mouseenter', () => {
                            btn.style.transform = 'scale(1.1)';
                            btn.style.borderColor = 'var(--white)';
                        });
                        
                        btn.addEventListener('mouseleave', () => {
                            btn.style.transform = 'scale(1)';
                            btn.style.borderColor = 'var(--gray-700)';
                        });
                        
                        btn.addEventListener('click', (e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            
                            if (savedRange) {
                                state.editor.setSelection(savedRange);
                                state.editor.format('background', color === 'transparent' ? false : color);
                            }
                            
                            picker.remove();
                        });
                        
                        picker.appendChild(btn);
                    });
                    
                    document.body.appendChild(picker);
                    
                    setTimeout(() => {
                        const closeHandler = (e) => {
                            if (!picker.contains(e.target) && e.target !== backgroundButton) {
                                picker.remove();
                                document.removeEventListener('click', closeHandler);
                            }
                        };
                        document.addEventListener('click', closeHandler);
                    }, 0);
                });
            }
            
            // Handle text change events
            state.editor.on('text-change', function() {
                // Clear any existing timeout
                if (textChangeTimeout) {
                    clearTimeout(textChangeTimeout);
                }
                
                // Set a new timeout to analyze text after typing stops
                textChangeTimeout = setTimeout(() => {
                    // Get text content from the editor
                    const fullText = state.editor.getText();
                    if (fullText.trim().length > 100 && !state.isAnalyzing) {
                        analyzeDocumentContext(fullText);
                    }
                }, 1500);
            });
            
            // Handle selection change events
            state.editor.on('selection-change', function(range) {
                if (range) {
                    if (range.length > 0) {
                        // We have a selection
                        const selectedText = state.editor.getText(range.index, range.length);
                        
                        // Store selected text in state
                        state.selectedText = selectedText.trim();
                        
                        // Enable generate button
                        generateButton.disabled = false;
                        
                        // Show visual indication
                        textInput.classList.add('has-selection');
                    } else {
                        // Cursor changed position but no selection
                        state.selectedText = '';
                        generateButton.disabled = true;
                        textInput.classList.remove('has-selection');
                    }
                } else {
                    // Editor lost focus
                    state.selectedText = '';
                    textInput.classList.remove('has-selection');
                }
            });
            
            console.log('Quill editor initialized');
            
            // Add context menu
            const editorElement = document.querySelector('.ql-editor');
            editorElement.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                showContextMenu(e.clientX, e.clientY);
            });
        } catch (error) {
            console.error('Error initializing Quill editor:', error);
        }
    }
    
    // Context Menu
    function showContextMenu(x, y) {
        removeContextMenu();
        
        const menu = document.createElement('div');
        menu.id = 'context-menu';
        menu.style.cssText = `position: fixed; left: ${x}px; top: ${y}px; z-index: 9999;`;
        
        const selection = state.editor.getSelection();
        const hasSelection = selection && selection.length > 0;
        const hasHighlight = hasSelection && state.editor.getFormat(selection.index, selection.length).background;
        
        // Salvar seleção para uso posterior
        state.savedRange = selection;
        
        // Atualizar selectedText com o texto selecionado atual
        if (hasSelection) {
            state.selectedText = state.editor.getText(selection.index, selection.length).trim();
        }
        
        menu.innerHTML = `
            <div class="context-menu-item ${!hasSelection ? 'disabled' : ''}" data-action="mark-text">Marcar texto ▸</div>
            <div class="context-menu-item ${!hasHighlight ? 'disabled' : ''}" data-action="remove-highlight">Remover marcação</div>
            <div class="context-menu-divider"></div>
            <div class="context-menu-item" data-action="analyze">Analisar texto novamente</div>
            <div class="context-menu-divider"></div>
            <div class="context-menu-item ${!hasSelection ? 'disabled' : ''}" data-action="basic">Gerar cartão básico</div>
            <div class="context-menu-item ${!hasSelection ? 'disabled' : ''}" data-action="cloze">Gerar cartão cloze</div>
        `;
        
        document.body.appendChild(menu);
        
        const markTextItem = menu.querySelector('[data-action="mark-text"]');
        
        menu.querySelectorAll('.context-menu-item').forEach(item => {
            item.addEventListener('click', async (e) => {
                const action = e.target.dataset.action;
                if (e.target.classList.contains('disabled')) return;
                
                if (action === 'mark-text') {
                    e.stopPropagation();
                    showColorSubmenu(markTextItem);
                    return;
                }
                
                removeContextMenu();
                
                if (action === 'remove-highlight') {
                    if (state.savedRange) {
                        state.editor.setSelection(state.savedRange);
                        state.editor.format('background', false);
                    }
                } else if (action === 'analyze') {
                    const fullText = state.editor.getText();
                    if (fullText.trim().length > 100) {
                        await analyzeDocumentContext(fullText);
                    } else {
                        showNotification('Texto muito curto para análise', 'error');
                    }
                } else if (action === 'basic' || action === 'cloze') {
                    // Garantir que temos o texto selecionado atualizado
                    if (state.savedRange && state.savedRange.length > 0) {
                        state.selectedText = state.editor.getText(state.savedRange.index, state.savedRange.length).trim();
                        const cardTypeSelect = document.getElementById('cardTypeSelect');
                        cardTypeSelect.value = action;
                        await generateCardsFromSelection();
                    } else {
                        showNotification('Please select some text first.', 'error');
                    }
                }
            });
        });
        
        document.addEventListener('click', removeContextMenu, { once: true });
    }
    
    function showColorSubmenu(parentItem) {
        const existingSubmenu = document.getElementById('color-submenu');
        if (existingSubmenu) existingSubmenu.remove();
        
        const colors = [
            { color: '#fef08a', label: 'Amarelo' },
            { color: '#bbf7d0', label: 'Verde' },
            { color: '#bfdbfe', label: 'Azul' },
            { color: '#fbcfe8', label: 'Rosa' },
            { color: '#ddd6fe', label: 'Roxo' },
            { color: '#fed7aa', label: 'Laranja' }
        ];
        
        const submenu = document.createElement('div');
        submenu.id = 'color-submenu';
        submenu.className = 'context-submenu';
        
        const rect = parentItem.getBoundingClientRect();
        submenu.style.cssText = `
            position: fixed;
            left: ${rect.right + 5}px;
            top: ${rect.top}px;
            z-index: 10000;
        `;
        
        colors.forEach(({ color, label }) => {
            const item = document.createElement('div');
            item.className = 'context-menu-item color-item';
            item.innerHTML = `<span class="color-dot" style="background-color: ${color};"></span>${label}`;
            item.addEventListener('mousedown', (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
            item.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (state.savedRange) {
                    state.editor.setSelection(state.savedRange);
                    state.editor.format('background', color);
                }
                removeContextMenu();
            });
            submenu.appendChild(item);
        });
        
        document.body.appendChild(submenu);
    }
    
    function removeContextMenu() {
        const menu = document.getElementById('context-menu');
        if (menu) menu.remove();
        const submenu = document.getElementById('color-submenu');
        if (submenu) submenu.remove();
    }
    
    // Handle selection for fallback editor
    function handleEditorSelection() {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        
        // Store selected text in state
        state.selectedText = selectedText;
        
        // Enable/disable buttons based on selection
        const hasSelection = selectedText.length > 0;
        generateButton.disabled = !hasSelection;
        
        // Show a visual indication of selection
        if (hasSelection) {
            textInput.classList.add('has-selection');
        } else {
            textInput.classList.remove('has-selection');
        }
    }
    
    // Fetch decks from Mochi API
    async function fetchDecks() {
        try {
            // Check if we have a client-side Mochi API key
            const { mochiApiKey } = getStoredApiKeys();
            
            if (!mochiApiKey) {
                // Use fallback decks when no Mochi API key is available
                state.decks = { "General": "general" };
                state.currentDeck = "General";
                
                // Update export button text
                const exportButton = document.getElementById('exportButton');
                if (exportButton) {
                    exportButton.textContent = 'Export as Markdown';
                }
                
                return;
            }
            
            // First try to use the server endpoint with user's API key
            try {
                // Pass the user's Mochi API key to the server endpoint
                const response = await fetch(`/api/mochi-decks?userMochiKey=${encodeURIComponent(mochiApiKey)}`);
                
                if (response.ok) {
                    const data = await response.json();
                    
                    if (data.success && data.decks) {
                        // Store the decks in the state
                        state.decks = data.decks;
                        
                        // Set currentDeck to first deck in the list
                        state.currentDeck = Object.keys(data.decks)[0] || "General";
                        // Decks loaded successfully
                        return;
                    }
                }
            } catch (serverError) {
                // Server-side API failed, trying client-side API next
            }
            
            // If server-side fails, try client-side API
            if (mochiApiKey) {
                // Mochi uses HTTP Basic Auth with API key followed by colon
                const authHeader = `Basic ${btoa(`${mochiApiKey}:`)}`;
                
                try {
                    // Directly call Mochi API from the client
                    const response = await fetch('https://app.mochi.cards/api/decks/', {
                        method: 'GET',
                        headers: {
                            'Authorization': authHeader
                        }
                    });
                    
                    if (!response.ok) {
                        throw new Error(`Mochi API Error: ${await response.text()}`);
                    }
                    
                    const decksData = await response.json();
                    
                    // Transform data for client use
                    const formattedDecks = {};
                    let activeDecksCount = 0;
                    
                    decksData.docs.forEach(deck => {
                        // Skip decks that are in trash or archived
                        if (deck['trashed?'] || deck['archived?']) {
                            return; // Skip this deck
                        }
                        
                        // Only include active decks
                        activeDecksCount++;
                        
                        // Remove [[ ]] if present in the ID
                        const cleanId = deck.id.replace(/\[\[|\]\]/g, '');
                        formattedDecks[deck.name] = cleanId;
                    });
                    
                    // Successfully loaded active decks from Mochi API
                    
                    // Store the decks in the state
                    state.decks = formattedDecks;
                    
                    // Set currentDeck to first deck in the list
                    state.currentDeck = Object.keys(formattedDecks)[0] || "General";
                    
                    // Update export button text
                    const exportButton = document.getElementById('exportButton');
                    if (exportButton) {
                        exportButton.textContent = 'Export to Mochi';
                    }
                    
                    return;
                } catch (clientApiError) {
                    console.error('Error using client-side Mochi API:', clientApiError);
                }
            }
            
            // Create deck selector dropdown
            createDeckSelector();
            
        } catch (error) {
            console.error('Error fetching decks:', error);
            // Fallback to a simple deck structure
            state.decks = { "General": "general" };
            state.currentDeck = "General";
            
            // Create deck selector with fallback
            createDeckSelector();
        }
    }
    
    // Function to show status notifications
    function showNotification(message, type = 'info', duration = 3000) {
        // Remove any existing notification
        const existingNotification = document.querySelector('.status-notification');
        if (existingNotification) {
            existingNotification.remove();
        }
        
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `status-notification ${type}`;
        
        // Add icon
        const icon = document.createElement('span');
        icon.className = 'icon';
        notification.appendChild(icon);
        
        // Add message
        const messageEl = document.createElement('span');
        messageEl.textContent = message;
        notification.appendChild(messageEl);
        
        // Add to document
        document.body.appendChild(notification);
        
        // Show notification with animation
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);
        
        // Hide after duration
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                notification.remove();
            }, 300);
        }, duration);
        
        return notification;
    }
    
    // Event Listeners
    generateButton.addEventListener('click', generateCardsFromSelection);
    exportButton.addEventListener('click', exportToMochi);
    const exportAnkiButton = document.getElementById('exportAnkiButton');
    exportAnkiButton.addEventListener('click', exportToAnki);
    clearCardsButton.addEventListener('click', clearAllCards);
    
    // Initialize Quill editor
    let textChangeTimeout = null;
    try {
        // Initialize the Quill editor
        initQuillEditor();
        
        // Quill handles paste events automatically
        // We'll analyze text after paste in the text-change handler
    } catch (error) {
        console.error('Failed to initialize Quill editor, falling back to basic contenteditable', error);
        // Fallback to basic contenteditable if Quill fails
        textInput.setAttribute('contenteditable', 'true');
        textInput.setAttribute('placeholder', 'Paste or type your text here, then highlight sections to generate cards...');
        
        // Add basic event listeners
        textInput.addEventListener('mouseup', handleEditorSelection);
        textInput.addEventListener('keyup', handleEditorSelection);
        textInput.addEventListener('input', () => {
            // Clear any existing timeout
            if (textChangeTimeout) {
                clearTimeout(textChangeTimeout);
            }
            
            // Set a new timeout to analyze text after typing stops
            textChangeTimeout = setTimeout(() => {
                const fullText = textInput.textContent || '';
                if (fullText.trim().length > 100 && !state.isAnalyzing) {
                    analyzeDocumentContext(fullText);
                }
            }, 1500);
        });
        
        // Add plain text paste handler for fallback
        textInput.addEventListener('paste', async function(e) {
            // Prevent the default paste behavior
            e.preventDefault();
            
            // Get plain text from clipboard
            const text = e.clipboardData.getData('text/plain');
            
            // Insert it at the cursor position using the standard command
            document.execCommand('insertText', false, text);
            
            // If text is long enough, analyze it immediately
            if (text.length > 100) {
                state.fromPaste = true;
                await analyzeDocumentContext(text);
            }
        });
    }
    
    // Enable the button if there's already text in the selection (Quill handles this now)
    // handleTextSelection() is now replaced by Quill's selection-change event
    
    // Initialize UI and fetch decks
    updateButtonStates();
    
    // Fetch decks from Mochi API on startup
    fetchDecks().catch(error => {
        console.error('Error initializing decks:', error);
        // Create a fallback deck selector in case of error
        createDeckSelector();
    });
    
    // We no longer need a deck selector in the main UI - we'll only show it when editing a card
    function createDeckSelector() {
        // Simply set the default current deck if none is set yet
        if (!state.currentDeck && Object.keys(state.decks).length > 0) {
            state.currentDeck = Object.keys(state.decks)[0];
        }
        // No UI elements to create here anymore
    }
    
    // Set up the resizable splitter
    let isResizing = false;
    let startY, startHeight;
    
    splitterHandle.addEventListener('mousedown', (e) => {
        isResizing = true;
        startY = e.clientY;
        startHeight = editorPanel.offsetHeight;
        
        document.documentElement.style.cursor = 'row-resize';
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', stopResize);
        e.preventDefault();
    });
    
    function handleMouseMove(e) {
        if (!isResizing) return;
        
        const container = document.querySelector('.dynamic-container');
        const containerHeight = container.offsetHeight;
        const deltaY = e.clientY - startY;
        const newEditorHeight = startHeight + deltaY;
        
        // Calculate editor height as percentage of container
        const editorHeightPercentage = (newEditorHeight / containerHeight) * 100;
        
        // Don't allow editor to be smaller than 20% or larger than 80% of container
        const minHeightPercentage = 20;
        const maxHeightPercentage = 80;
        
        if (editorHeightPercentage > minHeightPercentage && editorHeightPercentage < maxHeightPercentage) {
            // Use percentage for responsive sizing
            editorPanel.style.height = `${editorHeightPercentage}%`;
            
            // Calculate output panel height as the remaining percentage
            const outputHeightPercentage = 100 - editorHeightPercentage;
            outputPanel.style.height = `${outputHeightPercentage}%`;
        }
    }
    
    function stopResize() {
        if (isResizing) {
            isResizing = false;
            document.documentElement.style.cursor = '';
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', stopResize);
        }
    }
    
    // Prevent scrolling the page when mouse wheel is used over the text input
    textInput.addEventListener('wheel', function(e) {
        const contentHeight = this.scrollHeight;
        const visibleHeight = this.clientHeight;
        const scrollTop = this.scrollTop;
        
        // Check if we're at the top or bottom boundary
        const isAtTop = scrollTop === 0;
        const isAtBottom = scrollTop + visibleHeight >= contentHeight - 1;
        
        // If we're at a boundary and trying to scroll further in that direction, 
        // let the page scroll normally
        if ((isAtTop && e.deltaY < 0) || (isAtBottom && e.deltaY > 0)) {
            return;
        }
        
        // Otherwise, scroll the text input and prevent page scrolling
        e.preventDefault();
        this.scrollTop += e.deltaY;
    }, { passive: false });
    
    // Functions
    // Analyze text to extract context summary when text is pasted
    async function analyzeDocumentContext(text) {
        if (!text || text.trim().length < 100 || state.isAnalyzing) {
            return; // Skip short texts or if already analyzing
        }
        
        try {
            // Set analyzing state flag
            state.isAnalyzing = true;
            
            // Only disable the button if there's no selection
            if (!state.selectedText || state.selectedText.length === 0) {
                generateButton.disabled = true;
            }
            
            // Start timer
            startTimer('Analyzing text...');
            addLog('Starting text analysis...', 'info');
            
            const contextSummary = await analyzeTextWithClaude(text);
            addLog('Text analysis completed', 'success');
            
            if (contextSummary) {
                // Store in state for later use
                state.documentContext = contextSummary;
                
                // Show a subtle visual indicator that context is available
                document.body.classList.add('has-document-context');
            }
            
            state.fromPaste = false;
            stopTimer();
            showNotification('Text analysis complete. Card quality will be improved.', 'success', 4000);
        } catch (error) {
            console.error('Error analyzing document:', error);
            addLog('Analysis error: ' + error.message, 'error');
            stopTimer();
            showNotification('Failed to analyze text: ' + error.message, 'error');
        } finally {
            // Reset analyzing state
            state.isAnalyzing = false;
            
            // Re-enable button if there's a selection
            const hasSelection = state.selectedText && state.selectedText.length > 0;
            generateButton.disabled = !hasSelection;
        }
    }
    
    // Function to clear all highlights - adapted for Quill
    function clearAllHighlights() {
        // Remove the selection class
        textInput.classList.remove('has-selection');
        
        // Clear any selection in Quill or fall back to window selection
        if (state.editor && state.editor.setSelection) {
            // Clear Quill selection
            state.editor.setSelection(null);
        } else {
            // Fallback to window selection
            window.getSelection().removeAllRanges();
        }
    }
    
    async function generateCardsFromSelection() {
        const selectedText = state.selectedText;
        
        if (!selectedText) {
            showNotification('Please select some text first.', 'error');
            return;
        }
        
        try {
            // Get selected card type
            const cardTypeSelect = document.getElementById('cardTypeSelect');
            const cardType = cardTypeSelect ? cardTypeSelect.value : 'basic';
            
            // Update UI to show processing state
            generateButton.disabled = true;
            generateButton.textContent = 'Generating...';
            startTimer('Generating cards...');
            addLog(`Starting card generation (${cardType})...`, 'info');
            
            const cards = await generateCardsWithStream(
                selectedText,
                Object.keys(state.decks).join(', '),
                state.documentContext,
                cardType,
                ({ stage, data }) => {
                    try {
                        if (stage === 'stage' && data && data.stage) {
                            const s = data.stage;
                            if (s === 'analysis_started') addLog('Stage: Analysis started', 'info');
                            else if (s === 'analysis_completed') addLog('Stage: Analysis completed', 'success');
                            else if (s === 'generation_started') addLog('Stage: Generation started', 'info');
                            else if (s === 'generation_completed') addLog('Stage: Generation completed', 'success');
                            else if (s === 'parsing_started') addLog('Stage: Parsing started', 'info');
                            else if (s === 'parsing_completed') addLog('Stage: Parsing completed', 'success');
                        }
                    } catch (e) { 
                        console.error('Progress error:', e);
                        addLog('Progress error: ' + e.message, 'error');
                    }
                }
            );
            addLog(`Generated ${cards.length} cards successfully`, 'success');
            
            // Add generated cards to state
            state.cards = [...state.cards, ...cards];
            
            // Update UI
            renderCards();
            updateButtonStates();
            
            showNotification(`${cards.length} cards created successfully`, 'success');
        } catch (error) {
            console.error('Error generating cards:', error);
            addLog('Generation error: ' + error.message, 'error');
            
            // Provide a more specific message for timeout errors
            if (error.message && error.message.includes('FUNCTION_INVOCATION_TIMEOUT')) {
                showNotification('The request timed out. Please select a smaller portion of text and try again.', 'error', 8000);
            } else if (error.message && error.message.includes('timed out')) {
                showNotification('The request timed out. Please select a smaller portion of text and try again.', 'error', 8000);
            } else {
                showNotification('Error generating cards: ' + (error.message || 'Please try again.'), 'error', 8000);
            }
        } finally {
            stopTimer();
            generateButton.disabled = false;
            generateButton.textContent = 'Create Cards';
        }
    }


    
    function renderCards() {
        cardsContainer.innerHTML = '';
        
        // Show or hide the cards section based on whether there are cards
        if (state.cards.length > 0) {
            // Show the output panel and splitter if they're hidden
            if (outputPanel.style.display === 'none') {
                // Show the splitter handle with animation
                splitterHandle.style.display = 'flex';
                splitterHandle.classList.add('animate-in');
                
                // Show the output panel
                outputPanel.style.display = 'flex';
                
                // Set the editor panel to 50% height
                editorPanel.style.height = '50%';
            }
            
            // Render each card
            state.cards.forEach((card, index) => {
                const cardElement = createCardElement(card, index);
                cardsContainer.appendChild(cardElement);
            });
        } else {
            // Hide the output panel and splitter if there are no cards
            splitterHandle.style.display = 'none';
            outputPanel.style.display = 'none';
            
            // Reset the editor panel to full height
            editorPanel.style.height = '100%';
        }
    }
    
    // renderQuestions function removed
    
    function createCardElement(card, index) {
        const cardDiv = document.createElement('div');
        cardDiv.className = 'card';
        
        // Sanitize the card data to ensure it's rendered properly
        const sanitizeHtml = (text) => {
            // Create a temporary div
            const tempDiv = document.createElement('div');
            // Set the text content (this escapes HTML)
            tempDiv.textContent = text;
            // Return the sanitized HTML
            return tempDiv.innerHTML;
        };
        
        // Ensure the content is properly formatted strings, not JSON objects
        const front = typeof card.front === 'string' ? sanitizeHtml(card.front) : sanitizeHtml(JSON.stringify(card.front));
        const back = typeof card.back === 'string' ? sanitizeHtml(card.back) : sanitizeHtml(JSON.stringify(card.back));
        const deck = typeof card.deck === 'string' ? sanitizeHtml(card.deck) : sanitizeHtml(JSON.stringify(card.deck));
        
        cardDiv.innerHTML = `
            <div class="card-header">
                <div class="card-header-left">
                    <span class="card-deck" title="Click to change deck">${deck}</span>
                </div>
                <div class="card-header-right">
                    <button class="delete-button" data-index="${index}" title="Delete Card">×</button>
                </div>
            </div>
            <div class="card-content">
                <div class="card-front">
                    <div class="card-text" contenteditable="true">${front}</div>
                </div>
                <div class="card-back">
                    <div class="card-text" contenteditable="true">${back}</div>
                </div>
            </div>
        `;
        
        // Add event listeners
        const deleteButton = cardDiv.querySelector('.delete-button');
        deleteButton.addEventListener('click', () => deleteCard(index));
        
        const deckLabel = cardDiv.querySelector('.card-deck');
        deckLabel.addEventListener('click', () => editCardDeck(index));
        
        // Make card content editable
        const frontText = cardDiv.querySelector('.card-front .card-text');
        const backText = cardDiv.querySelector('.card-back .card-text');
        
        frontText.addEventListener('blur', () => {
            // Get text content instead of innerHTML to avoid HTML injection
            state.cards[index].front = frontText.textContent;
        });
        
        backText.addEventListener('blur', () => {
            // Get text content instead of innerHTML to avoid HTML injection
            state.cards[index].back = backText.textContent;
        });
        
        return cardDiv;
    }
    
    // createQuestionElement function removed
    
    function deleteCard(index) {
        state.cards.splice(index, 1);
        renderCards();
        updateButtonStates();
    }
    
    // deleteQuestion function removed
    
    function editCardDeck(index) {
        const card = state.cards[index];
        const deckNames = Object.keys(state.decks);
        
        if (deckNames.length === 0) {
            showNotification('No decks available. Please check Mochi connection.', 'error');
            return;
        }
        
        // Create an improved modal dialog with a dropdown
        const modalOverlay = document.createElement('div');
        modalOverlay.className = 'modal-overlay';
        
        const modalContent = document.createElement('div');
        modalContent.className = 'modal-content';
        
        const modalHeader = document.createElement('h3');
        modalHeader.textContent = 'Select Deck';
        
        const modalSubHeader = document.createElement('p');
        modalSubHeader.className = 'modal-subheader';
        modalSubHeader.textContent = 'Choose a deck for this card:';
        
        // Create a styled select element
        const selectContainer = document.createElement('div');
        selectContainer.className = 'modal-select-container';
        
        const deckSelect = document.createElement('select');
        deckSelect.className = 'deck-select';
        
        // Add a refresh button
        const refreshButton = document.createElement('button');
        refreshButton.className = 'modal-refresh-button';
        refreshButton.title = 'Refresh deck list from Mochi';
        refreshButton.innerHTML = '↻';
        refreshButton.addEventListener('click', () => {
            refreshButton.disabled = true;
            
            fetchDecks().then(() => {
                // Update the select options
                deckSelect.innerHTML = '';
                const updatedDeckNames = Object.keys(state.decks).sort((a, b) => 
                    a.localeCompare(b, undefined, { sensitivity: 'base' })
                );
                
                updatedDeckNames.forEach(deckName => {
                    const option = document.createElement('option');
                    option.value = deckName;
                    option.textContent = deckName;
                    if (deckName === card.deck) {
                        option.selected = true;
                    }
                    deckSelect.appendChild(option);
                });
                
                // Show confirmation
                refreshButton.innerHTML = '✓';
                setTimeout(() => {
                    refreshButton.innerHTML = '↻';
                    refreshButton.disabled = false;
                }, 1500);
                
                showNotification(`${updatedDeckNames.length} decks loaded`, 'success');
            }).catch(error => {
                console.error('Error refreshing decks:', error);
                refreshButton.innerHTML = '✗';
                setTimeout(() => {
                    refreshButton.innerHTML = '↻';
                    refreshButton.disabled = false;
                }, 1500);
                
                showNotification('Failed to refresh decks', 'error');
            });
        });
        
        // Get deck names and sort them alphabetically
        const sortedDeckNames = deckNames.sort((a, b) => 
            a.localeCompare(b, undefined, { sensitivity: 'base' })
        );
        
        // Add options based on available decks
        sortedDeckNames.forEach(deckName => {
            const option = document.createElement('option');
            option.value = deckName;
            option.textContent = deckName;
            if (deckName === card.deck) {
                option.selected = true;
            }
            deckSelect.appendChild(option);
        });
        
        selectContainer.appendChild(deckSelect);
        selectContainer.appendChild(refreshButton);
        
        // Create button container
        const buttonContainer = document.createElement('div');
        buttonContainer.className = 'modal-buttons';
        
        const cancelButton = document.createElement('button');
        cancelButton.textContent = 'Cancel';
        cancelButton.className = 'modal-cancel';
        cancelButton.addEventListener('click', () => {
            document.body.removeChild(modalOverlay);
        });
        
        const saveButton = document.createElement('button');
        saveButton.textContent = 'Update Deck';
        saveButton.className = 'modal-save';
        saveButton.addEventListener('click', () => {
            const oldDeck = card.deck;
            card.deck = deckSelect.value;
            renderCards();
            document.body.removeChild(modalOverlay);
            
            if (oldDeck !== card.deck) {
                showNotification(`Card moved to "${card.deck}" deck`, 'success');
            }
        });
        
        buttonContainer.appendChild(cancelButton);
        buttonContainer.appendChild(saveButton);
        
        // Assemble the modal
        modalContent.appendChild(modalHeader);
        modalContent.appendChild(modalSubHeader);
        modalContent.appendChild(selectContainer);
        modalContent.appendChild(buttonContainer);
        
        modalOverlay.appendChild(modalContent);
        document.body.appendChild(modalOverlay);
    }
    
    function updateButtonStates() {
        // Update card-related buttons based on whether cards exist
        const hasCards = state.cards.length > 0;
        exportButton.disabled = !hasCards;
        exportAnkiButton.disabled = !hasCards;
        clearCardsButton.disabled = !hasCards;
        
        // Update create cards button based on text selection
        const hasSelection = state.selectedText && state.selectedText.length > 0;
        generateButton.disabled = !hasSelection;
    }
    
    function clearAllCards() {
        // Simply clear all cards without confirmation
        state.cards = [];
        renderCards(); // This will hide the output panel and restore full height to editor
        updateButtonStates();
        showNotification('All cards cleared', 'info');
    }
    
    // clearAllQuestions function removed
    
    
    async function exportToMochi() {
        try {
            // Check if we have any cards to export
            if (state.cards.length === 0) {
                showNotification('No cards to export', 'info');
                return;
            }
            
            // Get the stored API keys
            const { mochiApiKey } = getStoredApiKeys();
            
            // If no Mochi API key, export as markdown instead
            if (!mochiApiKey) {
                exportAsMarkdown();
                return;
            }
            
            // If we have a Mochi API key, prepare the cards for Mochi
            const mochiData = formatCardsForMochi();
            const cards = JSON.parse(mochiData).cards;
            
            // Show loading indicator
            exportButton.disabled = true;
            exportButton.textContent = 'Uploading...';
            
            // Use the server endpoint to handle Mochi uploads, passing the user's API key
            const response = await fetch('/api/upload-to-mochi', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    cards,
                    userMochiKey: mochiApiKey // Pass the user's Mochi API key to the server
                })
            });
            
            if (!response.ok) {
                throw new Error('Failed to upload to Mochi');
            }
            
            const result = await response.json();
            
            // Success notification
            showNotification(`${result.totalSuccess} of ${result.totalCards} cards uploaded to Mochi successfully!`, 'success');
            
        } catch (error) {
            console.error('Error uploading to Mochi API:', error);
            showNotification('Error uploading to Mochi. Exporting as markdown instead.', 'error');
            
            // Fall back to markdown export
            exportAsMarkdown();
        } finally {
            // Reset button state
            exportButton.disabled = false;
            
            // Update button text based on whether we have a Mochi API key
            const { mochiApiKey } = getStoredApiKeys();
            exportButton.textContent = mochiApiKey ? 'Export to Mochi' : 'Export as Markdown';
        }
    }
    
    function exportAsMarkdown() {
        if (state.cards.length === 0) {
            showNotification('No cards to export', 'info');
            return;
        }
        
        // Format cards as markdown
        let markdown = `# Flashcards - ${new Date().toLocaleDateString()}\n\n`;
        
        // Group cards by deck
        const deckGroups = {};
        
        state.cards.forEach(card => {
            const deckName = card.deck || 'General';
            if (!deckGroups[deckName]) {
                deckGroups[deckName] = [];
            }
            deckGroups[deckName].push(card);
        });
        
        // Add each deck's cards to the markdown
        for (const [deckName, cards] of Object.entries(deckGroups)) {
            markdown += `## ${deckName}\n\n`;
            
            cards.forEach((card, index) => {
                markdown += `### Card ${index + 1}\n\n`;
                markdown += `**Question:** ${card.front}\n\n`;
                markdown += `---\n\n`;
                markdown += `**Answer:** ${card.back}\n\n`;
            });
        }
        
        try {
            // Download the markdown file
            const blob = new Blob([markdown], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `flashcards-${new Date().toISOString().slice(0, 10)}.md`;
            a.style.display = 'none'; // Hide the element
            document.body.appendChild(a);
            a.click();
            
            // Cleanup
            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }, 100);
            
            showNotification(`${state.cards.length} cards exported as markdown`, 'success');
        } catch (error) {
            console.error('Error exporting markdown:', error);
            
            // Alternative method for environments where the download might be blocked
            const textarea = document.createElement('textarea');
            textarea.value = markdown;
            document.body.appendChild(textarea);
            textarea.select();
            
            try {
                document.execCommand('copy');
                showNotification('Export copied to clipboard instead (download failed)', 'warning');
            } catch (clipboardError) {
                console.error('Clipboard copy failed:', clipboardError);
                showNotification('Export failed. Check console for markdown content', 'error');
                console.log('MARKDOWN CONTENT:');
                console.log(markdown);
            }
            
            document.body.removeChild(textarea);
        }
    }
    
    // exportQuestions function removed
    
    function formatCardsForMochi() {
        // Group cards by deck
        const deckMap = {};
        
        state.cards.forEach(card => {
            const deckName = card.deck;
            const deckId = state.decks[deckName];
            
            if (!deckId) {
                console.warn(`No deck ID found for deck: ${deckName}`);
                return; // Skip this card
            }
            
            if (!deckMap[deckId]) {
                deckMap[deckId] = [];
            }
            
            // Use the exact Mochi format: front \n---\n back (single newlines)
            deckMap[deckId].push({
                content: `${card.front}\n---\n${card.back}`
            });
        });
        
        // Format according to Mochi's JSON format
        const data = {
            version: 2,
            cards: []
        };
        
        // Add cards with their deck IDs
        for (const [deckId, cards] of Object.entries(deckMap)) {
            cards.forEach(card => {
                data.cards.push({
                    ...card,
                    'deck-id': deckId
                });
            });
        }
        
        console.log('Formatted cards for Mochi:', data);
        return JSON.stringify(data, null, 2);
    }
    
    // Anki Config Modal
    const ankiConfigModal = document.getElementById('ankiConfigModal');
    const ankiModelSelect = document.getElementById('ankiModel');
    const ankiFrontField = document.getElementById('ankiFrontField');
    const ankiBackField = document.getElementById('ankiBackField');
    const ankiDeckField = document.getElementById('ankiDeckField');
    const ankiTags = document.getElementById('ankiTags');
    const ankiConfigCancel = document.getElementById('ankiConfigCancel');
    const ankiConfigExport = document.getElementById('ankiConfigExport');
    
    let ankiModelsData = null;
    
    ankiModelSelect.addEventListener('change', () => {
        const modelName = ankiModelSelect.value;
        const fields = ankiModelsData.models[modelName] || [];
        
        ankiFrontField.innerHTML = fields.map(f => `<option value="${f}">${f}</option>`).join('');
        ankiBackField.innerHTML = fields.map(f => `<option value="${f}">${f}</option>`).join('');
        
        if (fields.length > 1) ankiBackField.selectedIndex = 1;
    });
    
    ankiConfigCancel.addEventListener('click', () => {
        ankiConfigModal.style.display = 'none';
    });
    
    ankiConfigExport.addEventListener('click', async () => {
        try {
            ankiConfigExport.disabled = true;
            ankiConfigExport.textContent = 'Uploading...';
            addLog('Starting Anki export...', 'info');
            
            const response = await fetch('/api/upload-to-anki', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cards: state.cards,
                    modelName: ankiModelSelect.value,
                    frontField: ankiFrontField.value,
                    backField: ankiBackField.value,
                    deckName: ankiDeckField.value,
                    tags: ankiTags.value
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to upload to Anki');
            }
            
            const result = await response.json();
            addLog(`Anki export completed: ${result.totalSuccess}/${result.totalCards} cards`, 'success');
            showNotification(`${result.totalSuccess} of ${result.totalCards} cards uploaded to Anki!`, 'success');
            ankiConfigModal.style.display = 'none';
            
        } catch (error) {
            console.error('Error uploading to Anki:', error);
            addLog('Anki export error: ' + error.message, 'error');
            showNotification('Error uploading to Anki: ' + error.message, 'error', 8000);
        } finally {
            ankiConfigExport.disabled = false;
            ankiConfigExport.textContent = 'Export to Anki';
        }
    });
    
    async function exportToAnki() {
        try {
            if (state.cards.length === 0) {
                showNotification('No cards to export', 'info');
                return;
            }
            
            addLog('Fetching Anki models...', 'info');
            const response = await fetch('/api/anki-models');
            
            if (!response.ok) {
                throw new Error('Could not connect to Anki. Make sure Anki is running with AnkiConnect installed.');
            }
            
            ankiModelsData = await response.json();
            
            // Populate model select
            const modelNames = Object.keys(ankiModelsData.models);
            ankiModelSelect.innerHTML = modelNames.map(m => `<option value="${m}">${m}</option>`).join('');
            
            // Populate deck select
            ankiDeckField.innerHTML = '<option value="">Use card\'s deck</option>' + 
                ankiModelsData.decks.map(d => `<option value="${d}">${d}</option>`).join('');
            
            // Trigger change to populate fields
            ankiModelSelect.dispatchEvent(new Event('change'));
            
            // Show modal
            ankiConfigModal.style.display = 'flex';
            addLog('Anki configuration ready', 'success');
            
        } catch (error) {
            console.error('Error fetching Anki config:', error);
            addLog('Anki config error: ' + error.message, 'error');
            showNotification(error.message, 'error', 8000);
        }
    }
    
    function downloadExport(data, filename) {
        const blob = new Blob([data], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 0);
    }
});
