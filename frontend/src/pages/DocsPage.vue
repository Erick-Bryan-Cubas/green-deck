<!-- frontend/src/pages/DocsPage.vue -->
<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import Toolbar from 'primevue/toolbar'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import SelectButton from 'primevue/selectbutton'
import Tree from 'primevue/tree'
import ScrollPanel from 'primevue/scrollpanel'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import Divider from 'primevue/divider'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'

const router = useRouter()
const route = useRoute()
const toast = useToast()

// Code snippets for copy-to-clipboard
const codeSnippets = {
  wsUrl: 'ws://localhost:3000/ws/status',
  wsJson: `{
  "anki": {
    "connected": true,
    "version": "2.1.66",
    "url": "http://127.0.0.1:8765"
  },
  "ollama": {
    "connected": true,
    "host": "http://localhost:11434",
    "models": ["llama3.2", "qwen2.5"]
  }
}`,
  wsJs: `const ws = new WebSocket('ws://localhost:3000/ws/status');

ws.onmessage = (event) => {
  const status = JSON.parse(event.data);
  console.log('Anki:', status.anki.connected);
  console.log('Ollama:', status.ollama.models);
};

ws.onclose = () => {
  console.log('Connection closed');
};`,
  clone: `git clone https://github.com/Erick-Bryan-Cubas/green-deck.git
cd green-deck`,
  backendPip: `python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt`,
  backendPoetry: `poetry install`,
  frontendInstall: `cd frontend
npm install`,
  frontendBuild: `npm run build`,
  run: 'python run.py',
  ollamaInstall: 'curl -fsSL https://ollama.com/install.sh | sh',
  ollamaPull: 'ollama pull llama3.2',
  envFile: `# Ollama server URL
OLLAMA_HOST=http://localhost:11434

# AnkiConnect URL
ANKI_CONNECT_URL=http://127.0.0.1:8765

# Backend server port
PORT=3000`,
  ollamaServe: 'ollama serve'
}

// Language state
const langOptions = [
  { label: 'PT-BR', value: 'pt' },
  { label: 'EN', value: 'en' }
]
const currentLang = ref('pt')

// Search
const searchQuery = ref('')

// Active section
const activeSection = ref('intro')
const expandedKeys = ref({ 'getting-started': true })

// Navigation tree
const navTree = computed(() => [
  {
    key: 'getting-started',
    label: t('nav.gettingStarted'),
    icon: 'pi pi-home',
    children: [
      { key: 'intro', label: t('nav.introduction'), icon: 'pi pi-info-circle' },
      { key: 'installation', label: t('nav.installation'), icon: 'pi pi-download' },
      { key: 'configuration', label: t('nav.configuration'), icon: 'pi pi-cog' }
    ]
  },
  {
    key: 'user-guide',
    label: t('nav.userGuide'),
    icon: 'pi pi-book',
    children: [
      { key: 'generator', label: t('nav.generator'), icon: 'pi pi-bolt' },
      { key: 'browser', label: t('nav.browser'), icon: 'pi pi-list' },
      { key: 'dashboard', label: t('nav.dashboard'), icon: 'pi pi-chart-bar' },
      { key: 'immersive', label: t('nav.immersive'), icon: 'pi pi-eye' }
    ]
  },
  {
    key: 'integrations',
    label: t('nav.integrations'),
    icon: 'pi pi-link',
    children: [
      { key: 'anki', label: 'Anki', icon: 'pi pi-box' },
      { key: 'llm', label: t('nav.llmProviders'), icon: 'pi pi-microchip-ai' }
    ]
  },
  {
    key: 'api-section',
    label: 'API Reference',
    icon: 'pi pi-code',
    children: [
      { key: 'api-endpoints', label: 'Endpoints', icon: 'pi pi-server' },
      { key: 'api-websocket', label: 'WebSocket', icon: 'pi pi-sync' }
    ]
  },
  {
    key: 'help',
    label: t('nav.help'),
    icon: 'pi pi-question-circle',
    children: [
      { key: 'faq', label: 'FAQ', icon: 'pi pi-comments' },
      { key: 'troubleshooting', label: t('nav.troubleshooting'), icon: 'pi pi-wrench' }
    ]
  }
])

// Translations
const translations = {
  pt: {
    title: 'Documentacao',
    searchPlaceholder: 'Buscar na documentacao...',
    nav: {
      gettingStarted: 'Primeiros Passos',
      introduction: 'Introducao',
      installation: 'Instalacao',
      configuration: 'Configuracao',
      userGuide: 'Guia de Uso',
      generator: 'Gerador de Cards',
      browser: 'Browser de Cards',
      dashboard: 'Dashboard',
      immersive: 'Modo Imersivo',
      integrations: 'Integracoes',
      llmProviders: 'Provedores LLM',
      help: 'Ajuda',
      troubleshooting: 'Solucao de Problemas'
    },
    intro: {
      title: 'Bem-vindo ao Green Deck',
      subtitle: 'Gerador de Flashcards com IA para Aprendizado Espacado',
      description: 'Green Deck e uma aplicacao open-source que utiliza inteligencia artificial para gerar flashcards de alta qualidade a partir de textos, PDFs e documentos. Integra-se perfeitamente com o Anki para revisao espacada.',
      features: {
        title: 'Principais Funcionalidades',
        ai: 'Geracao de cards com IA (Ollama, OpenAI, Claude, Perplexity)',
        documents: 'Suporte a multiplos formatos (PDF, DOCX, PPTX, imagens com OCR)',
        types: 'Cards Basic e Cloze deletion',
        anki: 'Integracao direta com Anki via AnkiConnect',
        analytics: 'Dashboard com estatisticas e metricas de estudo',
        quality: 'Pipeline de qualidade (SuperMemo 20 rules)'
      },
      stack: {
        title: 'Stack Tecnologica',
        frontend: 'Frontend: Vue 3 + PrimeVue + Vite',
        backend: 'Backend: FastAPI + Python 3.12',
        database: 'Database: DuckDB (embedded)',
        ai: 'IA: Ollama (local) + APIs externas'
      }
    },
    installation: {
      title: 'Instalacao',
      requirements: {
        title: 'Requisitos do Sistema',
        python: 'Python 3.12 ou superior',
        node: 'Node.js 18+ (para desenvolvimento)',
        anki: 'Anki Desktop com AnkiConnect instalado',
        ollama: 'Ollama (opcional, para IA local)',
        gpu: 'GPU com CUDA (recomendado para Ollama)'
      },
      steps: {
        title: 'Passos de Instalacao',
        clone: '1. Clone o repositorio',
        backend: '2. Instale as dependencias do backend',
        backendOption1: 'Opcao A: Usando pip',
        backendOption2: 'Opcao B: Usando Poetry',
        frontend: '3. Instale as dependencias do frontend',
        frontendBuild: '4. Build do frontend (producao)',
        run: '5. Inicie a aplicacao'
      },
      ollama: {
        title: 'Instalando o Ollama',
        description: 'Ollama permite executar modelos de IA localmente sem custos.',
        install: 'Instale o Ollama',
        pull: 'Baixe um modelo recomendado',
        models: 'Modelos recomendados: llama3.2, qwen2.5, mistral'
      },
      ankiconnect: {
        title: 'Instalando o AnkiConnect',
        description: 'AnkiConnect e um plugin do Anki que permite integracao via API.',
        step1: '1. Abra o Anki Desktop',
        step2: '2. Va em Ferramentas > Complementos > Obter Complementos',
        step3: '3. Cole o codigo: 2055492159',
        step4: '4. Reinicie o Anki'
      }
    },
    configuration: {
      title: 'Configuracao',
      env: {
        title: 'Variaveis de Ambiente',
        description: 'Crie um arquivo .env na raiz do projeto com as seguintes variaveis:',
        ollamaHost: 'URL do servidor Ollama',
        ankiUrl: 'URL do AnkiConnect',
        port: 'Porta do servidor backend'
      },
      apikeys: {
        title: 'Chaves de API',
        description: 'Para usar provedores externos (OpenAI, Anthropic, Perplexity), configure as chaves na interface:',
        step1: '1. Clique no icone de chave no sidebar',
        step2: '2. Insira sua API key',
        step3: '3. As chaves sao salvas localmente no navegador',
        security: 'As chaves nunca sao enviadas ao servidor - sao passadas diretamente nas requisicoes.'
      }
    },
    generator: {
      title: 'Gerador de Flashcards',
      description: 'O Gerador e a funcionalidade principal do Green Deck. Permite criar flashcards de alta qualidade a partir de qualquer texto.',
      input: {
        title: 'Entrada de Conteudo',
        manual: 'Digite ou cole texto diretamente no editor',
        upload: 'Faca upload de documentos (PDF, DOCX, PPTX, Excel, HTML, Markdown)',
        ocr: 'Imagens sao processadas com OCR automaticamente'
      },
      selection: {
        title: 'Selecao de Conteudo',
        highlight: 'Destaque trechos importantes com o marcador',
        select: 'Selecione texto especifico para gerar cards',
        priority: 'Prioridade: Selecao > Destaques > Texto completo'
      },
      types: {
        title: 'Tipos de Cards',
        basic: 'Basic: Pergunta na frente, resposta no verso',
        cloze: 'Cloze: Texto com lacunas para completar {{c1::resposta}}',
        both: 'Ambos: Gera os dois tipos simultaneamente'
      },
      prompts: {
        title: 'Prompts Customizados',
        description: 'Personalize os prompts para controlar a geracao:',
        system: 'System Prompt: Define o comportamento base do modelo',
        guidelines: 'Guidelines: Regras de qualidade (SuperMemo 20 rules)',
        generation: 'Generation Prompt: Template para geracao de cards'
      },
      topics: {
        title: 'Analise de Topicos',
        description: 'O sistema pode analisar e segmentar seu texto por topicos:',
        auto: 'Deteccao automatica de definicoes, exemplos, conceitos',
        colors: 'Cada topico recebe uma cor para facil identificacao',
        navigate: 'Clique em um segmento para navegar ate ele no editor'
      }
    },
    browser: {
      title: 'Browser de Cards',
      description: 'Navegue, filtre e edite seus flashcards do Anki.',
      filters: {
        title: 'Filtros Disponiveis',
        deck: 'Por deck',
        status: 'Por status (Novo, Aprendendo, Revisao, Suspenso)',
        tags: 'Por tags',
        search: 'Busca textual'
      },
      actions: {
        title: 'Acoes',
        edit: 'Editar frente e verso do card',
        delete: 'Excluir cards',
        suspend: 'Suspender/reativar cards',
        bulk: 'Operacoes em lote'
      },
      syntax: {
        title: 'Sintaxe de Busca',
        examples: 'Exemplos de filtros avancados:'
      }
    },
    dashboard: {
      title: 'Dashboard de Estatisticas',
      description: 'Visualize metricas e estatisticas do seu estudo.',
      kpis: {
        title: 'KPIs Principais',
        total: 'Total de cards gerados',
        created: 'Cards criados no periodo',
        decks: 'Numero de decks',
        average: 'Media de cards por dia'
      },
      charts: {
        title: 'Graficos',
        line: 'Grafico de linha: Cards criados por dia',
        doughnut: 'Grafico de rosca: Distribuicao por status'
      },
      drilldown: {
        title: 'Drill-down',
        deck: 'Clique em um deck para ver detalhes',
        day: 'Clique em um dia para ver cards criados'
      }
    },
    immersive: {
      title: 'Modo de Leitura Imersiva',
      description: 'Leia seus textos em um ambiente focado, estilo Kindle.',
      features: {
        title: 'Funcionalidades',
        themes: 'Temas: Kindle (sepia), Dark, Light',
        font: 'Ajuste de tamanho de fonte',
        pages: 'Paginacao do conteudo',
        spread: 'Visualizacao em duas paginas',
        autohide: 'Controles auto-ocultaveis'
      }
    },
    anki: {
      title: 'Integracao com Anki',
      description: 'O Green Deck se integra diretamente com o Anki Desktop via AnkiConnect.',
      connection: {
        title: 'Verificando Conexao',
        status: 'O indicador no sidebar mostra o status da conexao',
        green: 'Verde: Conectado',
        red: 'Vermelho: Desconectado'
      },
      decks: {
        title: 'Gerenciamento de Decks',
        list: 'Lista todos os decks disponiveis',
        create: 'Cria novos decks automaticamente',
        select: 'Selecione o deck de destino antes de gerar'
      },
      sync: {
        title: 'Sincronizacao',
        auto: 'Cards sao enviados automaticamente apos geracao',
        batch: 'Suporte a envio em lote'
      }
    },
    llm: {
      title: 'Provedores de IA',
      description: 'O Green Deck suporta multiplos provedores de LLM.',
      ollama: {
        title: 'Ollama (Local)',
        description: 'Execute modelos localmente sem custos.',
        features: 'Gratuito, privado, sem limites de uso',
        gpu: 'Monitoramento de GPU/VRAM em tempo real',
        models: 'Modelos recomendados: llama3.2, qwen2.5, mistral, gemma2'
      },
      openai: {
        title: 'OpenAI',
        description: 'Use GPT-4, GPT-3.5-turbo via API.',
        setup: 'Configure sua API key no sidebar',
        models: 'Modelos: gpt-4o, gpt-4o-mini, gpt-3.5-turbo'
      },
      anthropic: {
        title: 'Anthropic (Claude)',
        description: 'Use modelos Claude via API.',
        models: 'Modelos: claude-3-5-sonnet, claude-3-5-haiku'
      },
      perplexity: {
        title: 'Perplexity',
        description: 'Use modelos Sonar via API.',
        models: 'Modelos: sonar, sonar-pro'
      }
    },
    faq: {
      title: 'Perguntas Frequentes',
      q1: {
        q: 'O Anki precisa estar aberto?',
        a: 'Sim, o Anki Desktop precisa estar aberto para que a integracao funcione via AnkiConnect.'
      },
      q2: {
        q: 'Posso usar sem GPU?',
        a: 'Sim, mas a geracao com Ollama sera mais lenta. Considere usar modelos menores como llama3.2:1b ou APIs externas.'
      },
      q3: {
        q: 'Os cards gerados sao de qualidade?',
        a: 'O Green Deck aplica um pipeline de qualidade baseado nas regras SuperMemo 20 e validacao por LLM.'
      },
      q4: {
        q: 'Minhas API keys sao seguras?',
        a: 'Sim, as chaves sao armazenadas apenas no localStorage do seu navegador e enviadas diretamente aos provedores.'
      },
      q5: {
        q: 'Quais formatos de documento sao suportados?',
        a: 'PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc e imagens (PNG, JPG, TIFF, BMP) com OCR.'
      }
    },
    troubleshooting: {
      title: 'Solucao de Problemas',
      anki: {
        title: 'Problemas com Anki',
        notConnected: 'Anki nao conecta',
        notConnectedSolution: 'Verifique se o Anki Desktop esta aberto e o AnkiConnect instalado. Reinicie o Anki.',
        cors: 'Erro de CORS',
        corsSolution: 'Adicione "http://localhost:5173" e "http://localhost:3000" na config do AnkiConnect.'
      },
      ollama: {
        title: 'Problemas com Ollama',
        notRunning: 'Ollama nao detectado',
        notRunningSolution: 'Verifique se o servico esta rodando: ollama serve',
        slow: 'Geracao muito lenta',
        slowSolution: 'Use um modelo menor ou configure para usar GPU. Verifique VRAM disponivel.'
      },
      generation: {
        title: 'Problemas de Geracao',
        noCards: 'Nenhum card gerado',
        noCardsSolution: 'O texto pode ser muito curto ou irrelevante. Tente com conteudo mais denso.',
        badQuality: 'Cards de baixa qualidade',
        badQualitySolution: 'Ajuste os prompts customizados ou use um modelo mais capaz (GPT-4, Claude).'
      }
    },
    copySuccess: 'Codigo copiado!',
    copyError: 'Erro ao copiar',
    version: 'Versao'
  },
  en: {
    title: 'Documentation',
    searchPlaceholder: 'Search documentation...',
    nav: {
      gettingStarted: 'Getting Started',
      introduction: 'Introduction',
      installation: 'Installation',
      configuration: 'Configuration',
      userGuide: 'User Guide',
      generator: 'Card Generator',
      browser: 'Card Browser',
      dashboard: 'Dashboard',
      immersive: 'Immersive Mode',
      integrations: 'Integrations',
      llmProviders: 'LLM Providers',
      help: 'Help',
      troubleshooting: 'Troubleshooting'
    },
    intro: {
      title: 'Welcome to Green Deck',
      subtitle: 'AI-Powered Flashcard Generator for Spaced Repetition',
      description: 'Green Deck is an open-source application that uses artificial intelligence to generate high-quality flashcards from texts, PDFs, and documents. It integrates seamlessly with Anki for spaced repetition review.',
      features: {
        title: 'Key Features',
        ai: 'AI-powered card generation (Ollama, OpenAI, Claude, Perplexity)',
        documents: 'Multi-format support (PDF, DOCX, PPTX, images with OCR)',
        types: 'Basic and Cloze deletion cards',
        anki: 'Direct Anki integration via AnkiConnect',
        analytics: 'Dashboard with study statistics and metrics',
        quality: 'Quality pipeline (SuperMemo 20 rules)'
      },
      stack: {
        title: 'Technology Stack',
        frontend: 'Frontend: Vue 3 + PrimeVue + Vite',
        backend: 'Backend: FastAPI + Python 3.12',
        database: 'Database: DuckDB (embedded)',
        ai: 'AI: Ollama (local) + external APIs'
      }
    },
    installation: {
      title: 'Installation',
      requirements: {
        title: 'System Requirements',
        python: 'Python 3.12 or higher',
        node: 'Node.js 18+ (for development)',
        anki: 'Anki Desktop with AnkiConnect installed',
        ollama: 'Ollama (optional, for local AI)',
        gpu: 'GPU with CUDA (recommended for Ollama)'
      },
      steps: {
        title: 'Installation Steps',
        clone: '1. Clone the repository',
        backend: '2. Install backend dependencies',
        backendOption1: 'Option A: Using pip',
        backendOption2: 'Option B: Using Poetry',
        frontend: '3. Install frontend dependencies',
        frontendBuild: '4. Build frontend (production)',
        run: '5. Start the application'
      },
      ollama: {
        title: 'Installing Ollama',
        description: 'Ollama allows running AI models locally at no cost.',
        install: 'Install Ollama',
        pull: 'Download a recommended model',
        models: 'Recommended models: llama3.2, qwen2.5, mistral'
      },
      ankiconnect: {
        title: 'Installing AnkiConnect',
        description: 'AnkiConnect is an Anki plugin that enables API integration.',
        step1: '1. Open Anki Desktop',
        step2: '2. Go to Tools > Add-ons > Get Add-ons',
        step3: '3. Paste the code: 2055492159',
        step4: '4. Restart Anki'
      }
    },
    configuration: {
      title: 'Configuration',
      env: {
        title: 'Environment Variables',
        description: 'Create a .env file in the project root with the following variables:',
        ollamaHost: 'Ollama server URL',
        ankiUrl: 'AnkiConnect URL',
        port: 'Backend server port'
      },
      apikeys: {
        title: 'API Keys',
        description: 'To use external providers (OpenAI, Anthropic, Perplexity), configure keys in the interface:',
        step1: '1. Click the key icon in the sidebar',
        step2: '2. Enter your API key',
        step3: '3. Keys are saved locally in the browser',
        security: 'Keys are never sent to the server - they are passed directly in requests.'
      }
    },
    generator: {
      title: 'Flashcard Generator',
      description: 'The Generator is the main feature of Green Deck. It allows creating high-quality flashcards from any text.',
      input: {
        title: 'Content Input',
        manual: 'Type or paste text directly in the editor',
        upload: 'Upload documents (PDF, DOCX, PPTX, Excel, HTML, Markdown)',
        ocr: 'Images are processed with OCR automatically'
      },
      selection: {
        title: 'Content Selection',
        highlight: 'Highlight important passages with the marker',
        select: 'Select specific text to generate cards',
        priority: 'Priority: Selection > Highlights > Full text'
      },
      types: {
        title: 'Card Types',
        basic: 'Basic: Question on front, answer on back',
        cloze: 'Cloze: Text with blanks to fill {{c1::answer}}',
        both: 'Both: Generate both types simultaneously'
      },
      prompts: {
        title: 'Custom Prompts',
        description: 'Customize prompts to control generation:',
        system: 'System Prompt: Defines base model behavior',
        guidelines: 'Guidelines: Quality rules (SuperMemo 20 rules)',
        generation: 'Generation Prompt: Template for card generation'
      },
      topics: {
        title: 'Topic Analysis',
        description: 'The system can analyze and segment your text by topics:',
        auto: 'Automatic detection of definitions, examples, concepts',
        colors: 'Each topic gets a color for easy identification',
        navigate: 'Click a segment to navigate to it in the editor'
      }
    },
    browser: {
      title: 'Card Browser',
      description: 'Browse, filter, and edit your Anki flashcards.',
      filters: {
        title: 'Available Filters',
        deck: 'By deck',
        status: 'By status (New, Learning, Review, Suspended)',
        tags: 'By tags',
        search: 'Text search'
      },
      actions: {
        title: 'Actions',
        edit: 'Edit card front and back',
        delete: 'Delete cards',
        suspend: 'Suspend/unsuspend cards',
        bulk: 'Bulk operations'
      },
      syntax: {
        title: 'Search Syntax',
        examples: 'Advanced filter examples:'
      }
    },
    dashboard: {
      title: 'Statistics Dashboard',
      description: 'Visualize metrics and statistics from your study.',
      kpis: {
        title: 'Main KPIs',
        total: 'Total cards generated',
        created: 'Cards created in period',
        decks: 'Number of decks',
        average: 'Average cards per day'
      },
      charts: {
        title: 'Charts',
        line: 'Line chart: Cards created per day',
        doughnut: 'Doughnut chart: Distribution by status'
      },
      drilldown: {
        title: 'Drill-down',
        deck: 'Click a deck to see details',
        day: 'Click a day to see created cards'
      }
    },
    immersive: {
      title: 'Immersive Reading Mode',
      description: 'Read your texts in a focused environment, Kindle-style.',
      features: {
        title: 'Features',
        themes: 'Themes: Kindle (sepia), Dark, Light',
        font: 'Font size adjustment',
        pages: 'Content pagination',
        spread: 'Two-page spread view',
        autohide: 'Auto-hiding controls'
      }
    },
    anki: {
      title: 'Anki Integration',
      description: 'Green Deck integrates directly with Anki Desktop via AnkiConnect.',
      connection: {
        title: 'Checking Connection',
        status: 'The sidebar indicator shows connection status',
        green: 'Green: Connected',
        red: 'Red: Disconnected'
      },
      decks: {
        title: 'Deck Management',
        list: 'Lists all available decks',
        create: 'Creates new decks automatically',
        select: 'Select target deck before generating'
      },
      sync: {
        title: 'Synchronization',
        auto: 'Cards are sent automatically after generation',
        batch: 'Batch upload support'
      }
    },
    llm: {
      title: 'AI Providers',
      description: 'Green Deck supports multiple LLM providers.',
      ollama: {
        title: 'Ollama (Local)',
        description: 'Run models locally at no cost.',
        features: 'Free, private, no usage limits',
        gpu: 'Real-time GPU/VRAM monitoring',
        models: 'Recommended models: llama3.2, qwen2.5, mistral, gemma2'
      },
      openai: {
        title: 'OpenAI',
        description: 'Use GPT-4, GPT-3.5-turbo via API.',
        setup: 'Configure your API key in the sidebar',
        models: 'Models: gpt-4o, gpt-4o-mini, gpt-3.5-turbo'
      },
      anthropic: {
        title: 'Anthropic (Claude)',
        description: 'Use Claude models via API.',
        models: 'Models: claude-3-5-sonnet, claude-3-5-haiku'
      },
      perplexity: {
        title: 'Perplexity',
        description: 'Use Sonar models via API.',
        models: 'Models: sonar, sonar-pro'
      }
    },
    faq: {
      title: 'Frequently Asked Questions',
      q1: {
        q: 'Does Anki need to be open?',
        a: 'Yes, Anki Desktop needs to be open for the integration to work via AnkiConnect.'
      },
      q2: {
        q: 'Can I use without GPU?',
        a: 'Yes, but generation with Ollama will be slower. Consider using smaller models like llama3.2:1b or external APIs.'
      },
      q3: {
        q: 'Are generated cards quality?',
        a: 'Green Deck applies a quality pipeline based on SuperMemo 20 rules and LLM validation.'
      },
      q4: {
        q: 'Are my API keys secure?',
        a: 'Yes, keys are stored only in your browser localStorage and sent directly to providers.'
      },
      q5: {
        q: 'Which document formats are supported?',
        a: 'PDF, DOCX, PPTX, XLSX, HTML, Markdown, AsciiDoc, and images (PNG, JPG, TIFF, BMP) with OCR.'
      }
    },
    troubleshooting: {
      title: 'Troubleshooting',
      anki: {
        title: 'Anki Issues',
        notConnected: 'Anki not connecting',
        notConnectedSolution: 'Check if Anki Desktop is open and AnkiConnect is installed. Restart Anki.',
        cors: 'CORS error',
        corsSolution: 'Add "http://localhost:5173" and "http://localhost:3000" to AnkiConnect config.'
      },
      ollama: {
        title: 'Ollama Issues',
        notRunning: 'Ollama not detected',
        notRunningSolution: 'Check if the service is running: ollama serve',
        slow: 'Generation too slow',
        slowSolution: 'Use a smaller model or configure GPU usage. Check available VRAM.'
      },
      generation: {
        title: 'Generation Issues',
        noCards: 'No cards generated',
        noCardsSolution: 'Text may be too short or irrelevant. Try with denser content.',
        badQuality: 'Low quality cards',
        badQualitySolution: 'Adjust custom prompts or use a more capable model (GPT-4, Claude).'
      }
    },
    copySuccess: 'Code copied!',
    copyError: 'Copy failed',
    version: 'Version'
  }
}

// Translation helper
function t(key) {
  const keys = key.split('.')
  let result = translations[currentLang.value]
  for (const k of keys) {
    result = result?.[k]
  }
  return result || key
}

// API endpoints data
const apiEndpoints = computed(() => [
  {
    method: 'POST',
    path: '/api/generate-cards-stream',
    description: currentLang.value === 'pt' ? 'Gera flashcards com streaming' : 'Generate flashcards with streaming',
    curl: `curl -X POST http://localhost:3000/api/generate-cards-stream \\
  -H "Content-Type: application/json" \\
  -d '{"text": "Your text here", "deck": "Default", "card_type": "both"}'`
  },
  {
    method: 'POST',
    path: '/api/analyze-text-stream',
    description: currentLang.value === 'pt' ? 'Analisa texto com embeddings' : 'Analyze text with embeddings',
    curl: `curl -X POST http://localhost:3000/api/analyze-text-stream \\
  -H "Content-Type: application/json" \\
  -d '{"text": "Your text here", "mode": "embedding"}'`
  },
  {
    method: 'POST',
    path: '/api/segment-topics',
    description: currentLang.value === 'pt' ? 'Segmenta texto por topicos' : 'Segment text by topics',
    curl: `curl -X POST http://localhost:3000/api/segment-topics \\
  -H "Content-Type: application/json" \\
  -d '{"text": "Your text here"}'`
  },
  {
    method: 'GET',
    path: '/api/anki-decks',
    description: currentLang.value === 'pt' ? 'Lista decks do Anki' : 'List Anki decks',
    curl: `curl http://localhost:3000/api/anki-decks`
  },
  {
    method: 'POST',
    path: '/api/upload-to-anki',
    description: currentLang.value === 'pt' ? 'Envia cards para o Anki' : 'Upload cards to Anki',
    curl: `curl -X POST http://localhost:3000/api/upload-to-anki \\
  -H "Content-Type: application/json" \\
  -d '{"deck": "Default", "cards": [{"front": "Q", "back": "A"}]}'`
  },
  {
    method: 'GET',
    path: '/api/health',
    description: currentLang.value === 'pt' ? 'Status do servidor' : 'Server health status',
    curl: `curl http://localhost:3000/api/health`
  },
  {
    method: 'GET',
    path: '/api/ollama-status',
    description: currentLang.value === 'pt' ? 'Status do Ollama' : 'Ollama status',
    curl: `curl http://localhost:3000/api/ollama-status`
  },
  {
    method: 'GET',
    path: '/api/anki-status',
    description: currentLang.value === 'pt' ? 'Status do Anki' : 'Anki status',
    curl: `curl http://localhost:3000/api/anki-status`
  },
  {
    method: 'GET',
    path: '/api/dashboard/summary',
    description: currentLang.value === 'pt' ? 'Resumo do dashboard' : 'Dashboard summary',
    curl: `curl http://localhost:3000/api/dashboard/summary`
  },
  {
    method: 'POST',
    path: '/api/documents/extract',
    description: currentLang.value === 'pt' ? 'Extrai texto de documentos' : 'Extract text from documents',
    curl: `curl -X POST http://localhost:3000/api/documents/extract \\
  -F "file=@document.pdf"`
  }
])

// Search filter syntax examples
const searchSyntaxExamples = [
  { syntax: 'deck:"My Deck"', description: currentLang.value === 'pt' ? 'Filtrar por deck' : 'Filter by deck' },
  { syntax: 'is:new', description: currentLang.value === 'pt' ? 'Apenas cards novos' : 'Only new cards' },
  { syntax: 'is:learn', description: currentLang.value === 'pt' ? 'Cards em aprendizado' : 'Learning cards' },
  { syntax: 'is:review', description: currentLang.value === 'pt' ? 'Cards em revisao' : 'Review cards' },
  { syntax: 'is:suspended', description: currentLang.value === 'pt' ? 'Cards suspensos' : 'Suspended cards' },
  { syntax: 'tag:important', description: currentLang.value === 'pt' ? 'Filtrar por tag' : 'Filter by tag' }
]

// Copy to clipboard with fallback
function copyToClipboard(text) {
  // Fallback method using textarea
  const fallbackCopy = () => {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.left = '-9999px'
    textarea.style.top = '-9999px'
    document.body.appendChild(textarea)
    textarea.focus()
    textarea.select()
    try {
      document.execCommand('copy')
      toast.add({
        severity: 'success',
        summary: t('copySuccess'),
        life: 2000
      })
    } catch {
      toast.add({
        severity: 'error',
        summary: t('copyError'),
        life: 2000
      })
    }
    document.body.removeChild(textarea)
  }

  // Try modern API first, fallback if not available
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      toast.add({
        severity: 'success',
        summary: t('copySuccess'),
        life: 2000
      })
    }).catch(() => {
      fallbackCopy()
    })
  } else {
    fallbackCopy()
  }
}

// Handle tree node selection
function onNodeSelect(node) {
  if (node.key && !node.children) {
    activeSection.value = node.key
    // Update URL hash
    window.location.hash = node.key
  }
}

// Handle hash change
function handleHashChange() {
  const hash = window.location.hash.slice(1)
  if (hash) {
    activeSection.value = hash
    // Expand parent
    for (const parent of navTree.value) {
      if (parent.children?.some(c => c.key === hash)) {
        expandedKeys.value = { ...expandedKeys.value, [parent.key]: true }
        break
      }
    }
  }
}

// Filter tree by search
const filteredTree = computed(() => {
  if (!searchQuery.value) return navTree.value
  const query = searchQuery.value.toLowerCase()
  return navTree.value
    .map(parent => ({
      ...parent,
      children: parent.children?.filter(child =>
        child.label.toLowerCase().includes(query)
      )
    }))
    .filter(parent => parent.children?.length > 0)
})

// Sidebar collapsed state for mobile
const sidebarCollapsed = ref(false)

// Navigate back to generator
function goToGenerator() {
  router.push('/')
}

onMounted(() => {
  handleHashChange()
  window.addEventListener('hashchange', handleHashChange)
})

// Watch for language preference from localStorage
onMounted(() => {
  const savedLang = localStorage.getItem('docs-language')
  if (savedLang && ['pt', 'en'].includes(savedLang)) {
    currentLang.value = savedLang
  }
})

watch(currentLang, (newLang) => {
  localStorage.setItem('docs-language', newLang)
})
</script>

<template>
  <Toast />
  <div class="docs-page">
    <!-- Header Toolbar -->
    <Toolbar class="docs-toolbar">
      <template #start>
        <div class="toolbar-start">
          <Button
            icon="pi pi-arrow-left"
            text
            rounded
            @click="goToGenerator"
            v-tooltip.bottom="currentLang === 'pt' ? 'Voltar ao Gerador' : 'Back to Generator'"
          />
          <Button
            v-if="sidebarCollapsed"
            icon="pi pi-bars"
            text
            rounded
            @click="sidebarCollapsed = false"
            v-tooltip.bottom="currentLang === 'pt' ? 'Abrir menu' : 'Open menu'"
          />
          <img src="/green.svg" alt="Green Deck" class="docs-logo" />
          <span class="docs-title">{{ t('title') }}</span>
        </div>
      </template>
      <template #center>
        <div class="toolbar-center">
          <div class="search-wrapper">
            <i class="pi pi-search search-icon" />
            <InputText
              v-model="searchQuery"
              :placeholder="t('searchPlaceholder')"
              class="docs-search"
            />
          </div>
        </div>
      </template>
      <template #end>
        <div class="toolbar-end">
          <SelectButton
            v-model="currentLang"
            :options="langOptions"
            optionLabel="label"
            optionValue="value"
            class="lang-selector"
          />
          <Button
            icon="pi pi-github"
            text
            rounded
            @click="() => window.open('https://github.com/Erick-Bryan-Cubas/green-deck', '_blank')"
            v-tooltip.bottom="'GitHub'"
          />
        </div>
      </template>
    </Toolbar>

    <!-- Main Content -->
    <div class="docs-container">
      <!-- Sidebar Navigation -->
      <aside class="docs-sidebar" :class="{ collapsed: sidebarCollapsed }">
        <Button
          :icon="sidebarCollapsed ? 'pi pi-chevron-right' : 'pi pi-chevron-left'"
          text
          rounded
          class="sidebar-toggle-btn"
          @click="sidebarCollapsed = !sidebarCollapsed"
        />
        <ScrollPanel class="sidebar-scroll">
          <Tree
            :value="filteredTree"
            v-model:expandedKeys="expandedKeys"
            selectionMode="single"
            @node-select="onNodeSelect"
            class="docs-tree"
          >
            <template #default="{ node }">
              <span class="tree-label" :class="{ active: node.key === activeSection }">{{ node.label }}</span>
            </template>
          </Tree>
        </ScrollPanel>
      </aside>

      <!-- Content Area -->
      <main class="docs-content">
        <ScrollPanel class="content-scroll">
          <!-- Introduction -->
          <section v-if="activeSection === 'intro'" class="doc-section">
            <h1><i class="pi pi-home"></i> {{ t('intro.title') }}</h1>
            <p class="subtitle">{{ t('intro.subtitle') }}</p>
            <p class="description">{{ t('intro.description') }}</p>

            <Divider />

            <h2><i class="pi pi-star"></i> {{ t('intro.features.title') }}</h2>
            <ul class="feature-list">
              <li><i class="pi pi-microchip-ai"></i> {{ t('intro.features.ai') }}</li>
              <li><i class="pi pi-file"></i> {{ t('intro.features.documents') }}</li>
              <li><i class="pi pi-clone"></i> {{ t('intro.features.types') }}</li>
              <li><i class="pi pi-box"></i> {{ t('intro.features.anki') }}</li>
              <li><i class="pi pi-chart-bar"></i> {{ t('intro.features.analytics') }}</li>
              <li><i class="pi pi-check-circle"></i> {{ t('intro.features.quality') }}</li>
            </ul>

            <Divider />

            <h2><i class="pi pi-server"></i> {{ t('intro.stack.title') }}</h2>
            <ul class="stack-list">
              <li><Tag severity="success">Vue</Tag> {{ t('intro.stack.frontend') }}</li>
              <li><Tag severity="info">Python</Tag> {{ t('intro.stack.backend') }}</li>
              <li><Tag severity="warn">DuckDB</Tag> {{ t('intro.stack.database') }}</li>
              <li><Tag severity="secondary">Ollama</Tag> {{ t('intro.stack.ai') }}</li>
            </ul>
          </section>

          <!-- Installation -->
          <section v-if="activeSection === 'installation'" class="doc-section">
            <h1><i class="pi pi-download"></i> {{ t('installation.title') }}</h1>

            <h2><i class="pi pi-list"></i> {{ t('installation.requirements.title') }}</h2>
            <ul class="requirements-list">
              <li><i class="pi pi-check"></i> {{ t('installation.requirements.python') }}</li>
              <li><i class="pi pi-check"></i> {{ t('installation.requirements.node') }}</li>
              <li><i class="pi pi-check"></i> {{ t('installation.requirements.anki') }}</li>
              <li><i class="pi pi-check"></i> {{ t('installation.requirements.ollama') }}</li>
              <li><i class="pi pi-check"></i> {{ t('installation.requirements.gpu') }}</li>
            </ul>

            <Divider />

            <h2><i class="pi pi-cog"></i> {{ t('installation.steps.title') }}</h2>

            <h3>{{ t('installation.steps.clone') }}</h3>
            <div class="code-block">
              <div class="code-header">
                <span>bash</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.clone)" />
              </div>
              <pre><code>{{ codeSnippets.clone }}</code></pre>
            </div>

            <h3>{{ t('installation.steps.backend') }}</h3>

            <h4><Tag severity="info" class="option-tag">A</Tag> {{ t('installation.steps.backendOption1') }}</h4>
            <div class="code-block">
              <div class="code-header">
                <span>bash</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.backendPip)" />
              </div>
              <pre><code>{{ codeSnippets.backendPip }}</code></pre>
            </div>

            <h4><Tag severity="success" class="option-tag">B</Tag> {{ t('installation.steps.backendOption2') }}</h4>
            <div class="code-block">
              <div class="code-header">
                <span>bash</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.backendPoetry)" />
              </div>
              <pre><code>{{ codeSnippets.backendPoetry }}</code></pre>
            </div>

            <h3>{{ t('installation.steps.frontend') }}</h3>
            <div class="code-block">
              <div class="code-header">
                <span>bash</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.frontendInstall)" />
              </div>
              <pre><code>{{ codeSnippets.frontendInstall }}</code></pre>
            </div>

            <h3>{{ t('installation.steps.frontendBuild') }}</h3>
            <div class="code-block">
              <div class="code-header">
                <span>bash</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.frontendBuild)" />
              </div>
              <pre><code>{{ codeSnippets.frontendBuild }}</code></pre>
            </div>

            <h3>{{ t('installation.steps.run') }}</h3>
            <div class="code-block">
              <div class="code-header">
                <span>bash</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.run)" />
              </div>
              <pre><code>{{ codeSnippets.run }}</code></pre>
            </div>

            <Divider />

            <h2><i class="pi pi-box"></i> {{ t('installation.ollama.title') }}</h2>
            <p>{{ t('installation.ollama.description') }}</p>

            <h3>{{ t('installation.ollama.install') }}</h3>
            <div class="code-block">
              <div class="code-header">
                <span>bash</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.ollamaInstall)" />
              </div>
              <pre><code>{{ codeSnippets.ollamaInstall }}</code></pre>
            </div>

            <h3>{{ t('installation.ollama.pull') }}</h3>
            <div class="code-block">
              <div class="code-header">
                <span>bash</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.ollamaPull)" />
              </div>
              <pre><code>{{ codeSnippets.ollamaPull }}</code></pre>
            </div>
            <Message severity="info" :closable="false">
              {{ t('installation.ollama.models') }}
            </Message>

            <Divider />

            <h2><i class="pi pi-link"></i> {{ t('installation.ankiconnect.title') }}</h2>
            <p>{{ t('installation.ankiconnect.description') }}</p>
            <ol class="steps-list">
              <li>{{ t('installation.ankiconnect.step1') }}</li>
              <li>{{ t('installation.ankiconnect.step2') }}</li>
              <li>{{ t('installation.ankiconnect.step3') }}</li>
              <li>{{ t('installation.ankiconnect.step4') }}</li>
            </ol>
          </section>

          <!-- Configuration -->
          <section v-if="activeSection === 'configuration'" class="doc-section">
            <h1><i class="pi pi-cog"></i> {{ t('configuration.title') }}</h1>

            <h2><i class="pi pi-file"></i> {{ t('configuration.env.title') }}</h2>
            <p>{{ t('configuration.env.description') }}</p>

            <div class="code-block">
              <div class="code-header">
                <span>.env</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.envFile)" />
              </div>
              <pre><code>{{ codeSnippets.envFile }}</code></pre>
            </div>

            <Divider />

            <h2><i class="pi pi-key"></i> {{ t('configuration.apikeys.title') }}</h2>
            <p>{{ t('configuration.apikeys.description') }}</p>
            <ol class="steps-list">
              <li>{{ t('configuration.apikeys.step1') }}</li>
              <li>{{ t('configuration.apikeys.step2') }}</li>
              <li>{{ t('configuration.apikeys.step3') }}</li>
            </ol>
            <Message severity="success" :closable="false">
              <i class="pi pi-shield"></i> {{ t('configuration.apikeys.security') }}
            </Message>
          </section>

          <!-- Generator -->
          <section v-if="activeSection === 'generator'" class="doc-section">
            <h1><i class="pi pi-bolt"></i> {{ t('generator.title') }}</h1>
            <p class="description">{{ t('generator.description') }}</p>

            <Divider />

            <h2><i class="pi pi-file-edit"></i> {{ t('generator.input.title') }}</h2>
            <ul class="feature-list">
              <li><i class="pi pi-pencil"></i> {{ t('generator.input.manual') }}</li>
              <li><i class="pi pi-upload"></i> {{ t('generator.input.upload') }}</li>
              <li><i class="pi pi-image"></i> {{ t('generator.input.ocr') }}</li>
            </ul>

            <Divider />

            <h2><i class="pi pi-highlight"></i> {{ t('generator.selection.title') }}</h2>
            <ul class="feature-list">
              <li><i class="pi pi-palette"></i> {{ t('generator.selection.highlight') }}</li>
              <li><i class="pi pi-check-square"></i> {{ t('generator.selection.select') }}</li>
              <li><i class="pi pi-sort-amount-down"></i> {{ t('generator.selection.priority') }}</li>
            </ul>

            <Divider />

            <h2><i class="pi pi-clone"></i> {{ t('generator.types.title') }}</h2>
            <ul class="card-types-list">
              <li>
                <Tag severity="info">Basic</Tag>
                <span>{{ t('generator.types.basic') }}</span>
              </li>
              <li>
                <Tag severity="warn">Cloze</Tag>
                <span>{{ t('generator.types.cloze') }}</span>
              </li>
              <li>
                <Tag severity="success">Both</Tag>
                <span>{{ t('generator.types.both') }}</span>
              </li>
            </ul>

            <Divider />

            <h2><i class="pi pi-sliders-h"></i> {{ t('generator.prompts.title') }}</h2>
            <p>{{ t('generator.prompts.description') }}</p>
            <ul class="feature-list">
              <li><i class="pi pi-cog"></i> {{ t('generator.prompts.system') }}</li>
              <li><i class="pi pi-list-check"></i> {{ t('generator.prompts.guidelines') }}</li>
              <li><i class="pi pi-file"></i> {{ t('generator.prompts.generation') }}</li>
            </ul>

            <Divider />

            <h2><i class="pi pi-sitemap"></i> {{ t('generator.topics.title') }}</h2>
            <p>{{ t('generator.topics.description') }}</p>
            <ul class="feature-list">
              <li><i class="pi pi-search"></i> {{ t('generator.topics.auto') }}</li>
              <li><i class="pi pi-palette"></i> {{ t('generator.topics.colors') }}</li>
              <li><i class="pi pi-arrow-right"></i> {{ t('generator.topics.navigate') }}</li>
            </ul>
          </section>

          <!-- Browser -->
          <section v-if="activeSection === 'browser'" class="doc-section">
            <h1><i class="pi pi-list"></i> {{ t('browser.title') }}</h1>
            <p class="description">{{ t('browser.description') }}</p>

            <Divider />

            <h2><i class="pi pi-filter"></i> {{ t('browser.filters.title') }}</h2>
            <ul class="feature-list">
              <li><i class="pi pi-folder"></i> {{ t('browser.filters.deck') }}</li>
              <li><i class="pi pi-tag"></i> {{ t('browser.filters.status') }}</li>
              <li><i class="pi pi-hashtag"></i> {{ t('browser.filters.tags') }}</li>
              <li><i class="pi pi-search"></i> {{ t('browser.filters.search') }}</li>
            </ul>

            <Divider />

            <h2><i class="pi pi-cog"></i> {{ t('browser.actions.title') }}</h2>
            <ul class="feature-list">
              <li><i class="pi pi-pencil"></i> {{ t('browser.actions.edit') }}</li>
              <li><i class="pi pi-trash"></i> {{ t('browser.actions.delete') }}</li>
              <li><i class="pi pi-pause"></i> {{ t('browser.actions.suspend') }}</li>
              <li><i class="pi pi-check-square"></i> {{ t('browser.actions.bulk') }}</li>
            </ul>

            <Divider />

            <h2><i class="pi pi-code"></i> {{ t('browser.syntax.title') }}</h2>
            <p>{{ t('browser.syntax.examples') }}</p>
            <DataTable :value="searchSyntaxExamples" class="syntax-table">
              <Column field="syntax" header="Syntax">
                <template #body="{ data }">
                  <code class="syntax-code">{{ data.syntax }}</code>
                </template>
              </Column>
              <Column field="description" :header="currentLang === 'pt' ? 'Descricao' : 'Description'" />
            </DataTable>
          </section>

          <!-- Dashboard -->
          <section v-if="activeSection === 'dashboard'" class="doc-section">
            <h1><i class="pi pi-chart-bar"></i> {{ t('dashboard.title') }}</h1>
            <p class="description">{{ t('dashboard.description') }}</p>

            <Divider />

            <h2><i class="pi pi-chart-line"></i> {{ t('dashboard.kpis.title') }}</h2>
            <ul class="feature-list">
              <li><i class="pi pi-database"></i> {{ t('dashboard.kpis.total') }}</li>
              <li><i class="pi pi-plus-circle"></i> {{ t('dashboard.kpis.created') }}</li>
              <li><i class="pi pi-folder"></i> {{ t('dashboard.kpis.decks') }}</li>
              <li><i class="pi pi-calculator"></i> {{ t('dashboard.kpis.average') }}</li>
            </ul>

            <Divider />

            <h2><i class="pi pi-chart-pie"></i> {{ t('dashboard.charts.title') }}</h2>
            <ul class="feature-list">
              <li><i class="pi pi-chart-line"></i> {{ t('dashboard.charts.line') }}</li>
              <li><i class="pi pi-circle"></i> {{ t('dashboard.charts.doughnut') }}</li>
            </ul>

            <Divider />

            <h2><i class="pi pi-search-plus"></i> {{ t('dashboard.drilldown.title') }}</h2>
            <ul class="feature-list">
              <li><i class="pi pi-folder-open"></i> {{ t('dashboard.drilldown.deck') }}</li>
              <li><i class="pi pi-calendar"></i> {{ t('dashboard.drilldown.day') }}</li>
            </ul>
          </section>

          <!-- Immersive Mode -->
          <section v-if="activeSection === 'immersive'" class="doc-section">
            <h1><i class="pi pi-eye"></i> {{ t('immersive.title') }}</h1>
            <p class="description">{{ t('immersive.description') }}</p>

            <Divider />

            <h2><i class="pi pi-list"></i> {{ t('immersive.features.title') }}</h2>
            <ul class="feature-list">
              <li><i class="pi pi-palette"></i> {{ t('immersive.features.themes') }}</li>
              <li><i class="pi pi-text-height"></i> {{ t('immersive.features.font') }}</li>
              <li><i class="pi pi-book"></i> {{ t('immersive.features.pages') }}</li>
              <li><i class="pi pi-th-large"></i> {{ t('immersive.features.spread') }}</li>
              <li><i class="pi pi-eye-slash"></i> {{ t('immersive.features.autohide') }}</li>
            </ul>
          </section>

          <!-- Anki Integration -->
          <section v-if="activeSection === 'anki'" class="doc-section">
            <h1><i class="pi pi-box"></i> {{ t('anki.title') }}</h1>
            <p class="description">{{ t('anki.description') }}</p>

            <Divider />

            <h2><i class="pi pi-wifi"></i> {{ t('anki.connection.title') }}</h2>
            <p>{{ t('anki.connection.status') }}</p>
            <ul class="status-list">
              <li><span class="status-dot green"></span> {{ t('anki.connection.green') }}</li>
              <li><span class="status-dot red"></span> {{ t('anki.connection.red') }}</li>
            </ul>

            <Divider />

            <h2><i class="pi pi-folder"></i> {{ t('anki.decks.title') }}</h2>
            <ul class="feature-list">
              <li><i class="pi pi-list"></i> {{ t('anki.decks.list') }}</li>
              <li><i class="pi pi-plus"></i> {{ t('anki.decks.create') }}</li>
              <li><i class="pi pi-check"></i> {{ t('anki.decks.select') }}</li>
            </ul>

            <Divider />

            <h2><i class="pi pi-sync"></i> {{ t('anki.sync.title') }}</h2>
            <ul class="feature-list">
              <li><i class="pi pi-send"></i> {{ t('anki.sync.auto') }}</li>
              <li><i class="pi pi-clone"></i> {{ t('anki.sync.batch') }}</li>
            </ul>
          </section>

          <!-- LLM Providers -->
          <section v-if="activeSection === 'llm'" class="doc-section">
            <h1><i class="pi pi-microchip-ai"></i> {{ t('llm.title') }}</h1>
            <p class="description">{{ t('llm.description') }}</p>

            <Divider />

            <h2><i class="pi pi-desktop"></i> {{ t('llm.ollama.title') }}</h2>
            <p>{{ t('llm.ollama.description') }}</p>
            <ul class="feature-list">
              <li><i class="pi pi-check"></i> {{ t('llm.ollama.features') }}</li>
              <li><i class="pi pi-chart-bar"></i> {{ t('llm.ollama.gpu') }}</li>
            </ul>
            <Message severity="info" :closable="false">
              {{ t('llm.ollama.models') }}
            </Message>

            <Divider />

            <h2><i class="pi pi-cloud"></i> {{ t('llm.openai.title') }}</h2>
            <p>{{ t('llm.openai.description') }}</p>
            <p>{{ t('llm.openai.setup') }}</p>
            <Message severity="secondary" :closable="false">
              {{ t('llm.openai.models') }}
            </Message>

            <Divider />

            <h2><i class="pi pi-sparkles"></i> {{ t('llm.anthropic.title') }}</h2>
            <p>{{ t('llm.anthropic.description') }}</p>
            <Message severity="secondary" :closable="false">
              {{ t('llm.anthropic.models') }}
            </Message>

            <Divider />

            <h2><i class="pi pi-globe"></i> {{ t('llm.perplexity.title') }}</h2>
            <p>{{ t('llm.perplexity.description') }}</p>
            <Message severity="secondary" :closable="false">
              {{ t('llm.perplexity.models') }}
            </Message>
          </section>

          <!-- API Endpoints -->
          <section v-if="activeSection === 'api-endpoints'" class="doc-section">
            <h1><i class="pi pi-server"></i> API Endpoints</h1>
            <p class="description">
              {{ currentLang === 'pt' ? 'Referencia dos principais endpoints da API REST.' : 'Reference for main REST API endpoints.' }}
            </p>

            <DataTable :value="apiEndpoints" class="api-table" stripedRows>
              <Column field="method" header="Method" style="width: 100px">
                <template #body="{ data }">
                  <Tag :severity="data.method === 'GET' ? 'success' : 'info'">{{ data.method }}</Tag>
                </template>
              </Column>
              <Column field="path" header="Endpoint">
                <template #body="{ data }">
                  <code class="endpoint-code">{{ data.path }}</code>
                </template>
              </Column>
              <Column field="description" :header="currentLang === 'pt' ? 'Descricao' : 'Description'" />
            </DataTable>

            <Divider />

            <h2>{{ currentLang === 'pt' ? 'Exemplos de Requisicoes' : 'Request Examples' }}</h2>

            <div v-for="endpoint in apiEndpoints" :key="endpoint.path" class="endpoint-example">
              <h3>
                <Tag :severity="endpoint.method === 'GET' ? 'success' : 'info'" class="method-tag">{{ endpoint.method }}</Tag>
                <code>{{ endpoint.path }}</code>
              </h3>
              <div class="code-block">
                <div class="code-header">
                  <span>curl</span>
                  <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(endpoint.curl)" />
                </div>
                <pre><code>{{ endpoint.curl }}</code></pre>
              </div>
            </div>
          </section>

          <!-- WebSocket -->
          <section v-if="activeSection === 'api-websocket'" class="doc-section">
            <h1><i class="pi pi-sync"></i> WebSocket</h1>
            <p class="description">
              {{ currentLang === 'pt' ? 'Conexao WebSocket para atualizacoes de status em tempo real.' : 'WebSocket connection for real-time status updates.' }}
            </p>

            <h2>{{ currentLang === 'pt' ? 'Endpoint' : 'Endpoint' }}</h2>
            <div class="code-block">
              <div class="code-header">
                <span>WebSocket URL</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.wsUrl)" />
              </div>
              <pre><code>{{ codeSnippets.wsUrl }}</code></pre>
            </div>

            <Divider />

            <h2>{{ currentLang === 'pt' ? 'Formato das Mensagens' : 'Message Format' }}</h2>
            <div class="code-block">
              <div class="code-header">
                <span>JSON</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.wsJson)" />
              </div>
              <pre><code>{{ codeSnippets.wsJson }}</code></pre>
            </div>

            <Divider />

            <h2>{{ currentLang === 'pt' ? 'Exemplo JavaScript' : 'JavaScript Example' }}</h2>
            <div class="code-block">
              <div class="code-header">
                <span>JavaScript</span>
                <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.wsJs)" />
              </div>
              <pre><code>{{ codeSnippets.wsJs }}</code></pre>
            </div>
          </section>

          <!-- FAQ -->
          <section v-if="activeSection === 'faq'" class="doc-section">
            <h1><i class="pi pi-comments"></i> {{ t('faq.title') }}</h1>

            <div class="faq-list">
              <div class="faq-item">
                <h3><i class="pi pi-question-circle"></i> {{ t('faq.q1.q') }}</h3>
                <p>{{ t('faq.q1.a') }}</p>
              </div>

              <div class="faq-item">
                <h3><i class="pi pi-question-circle"></i> {{ t('faq.q2.q') }}</h3>
                <p>{{ t('faq.q2.a') }}</p>
              </div>

              <div class="faq-item">
                <h3><i class="pi pi-question-circle"></i> {{ t('faq.q3.q') }}</h3>
                <p>{{ t('faq.q3.a') }}</p>
              </div>

              <div class="faq-item">
                <h3><i class="pi pi-question-circle"></i> {{ t('faq.q4.q') }}</h3>
                <p>{{ t('faq.q4.a') }}</p>
              </div>

              <div class="faq-item">
                <h3><i class="pi pi-question-circle"></i> {{ t('faq.q5.q') }}</h3>
                <p>{{ t('faq.q5.a') }}</p>
              </div>
            </div>
          </section>

          <!-- Troubleshooting -->
          <section v-if="activeSection === 'troubleshooting'" class="doc-section">
            <h1><i class="pi pi-wrench"></i> {{ t('troubleshooting.title') }}</h1>

            <h2><i class="pi pi-box"></i> {{ t('troubleshooting.anki.title') }}</h2>
            <div class="troubleshoot-item">
              <h4><i class="pi pi-exclamation-triangle"></i> {{ t('troubleshooting.anki.notConnected') }}</h4>
              <p>{{ t('troubleshooting.anki.notConnectedSolution') }}</p>
            </div>
            <div class="troubleshoot-item">
              <h4><i class="pi pi-exclamation-triangle"></i> {{ t('troubleshooting.anki.cors') }}</h4>
              <p>{{ t('troubleshooting.anki.corsSolution') }}</p>
            </div>

            <Divider />

            <h2><i class="pi pi-desktop"></i> {{ t('troubleshooting.ollama.title') }}</h2>
            <div class="troubleshoot-item">
              <h4><i class="pi pi-exclamation-triangle"></i> {{ t('troubleshooting.ollama.notRunning') }}</h4>
              <p>{{ t('troubleshooting.ollama.notRunningSolution') }}</p>
              <div class="code-block">
                <div class="code-header">
                  <span>bash</span>
                  <Button icon="pi pi-copy" text size="small" @click="copyToClipboard(codeSnippets.ollamaServe)" />
                </div>
                <pre><code>{{ codeSnippets.ollamaServe }}</code></pre>
              </div>
            </div>
            <div class="troubleshoot-item">
              <h4><i class="pi pi-exclamation-triangle"></i> {{ t('troubleshooting.ollama.slow') }}</h4>
              <p>{{ t('troubleshooting.ollama.slowSolution') }}</p>
            </div>

            <Divider />

            <h2><i class="pi pi-bolt"></i> {{ t('troubleshooting.generation.title') }}</h2>
            <div class="troubleshoot-item">
              <h4><i class="pi pi-exclamation-triangle"></i> {{ t('troubleshooting.generation.noCards') }}</h4>
              <p>{{ t('troubleshooting.generation.noCardsSolution') }}</p>
            </div>
            <div class="troubleshoot-item">
              <h4><i class="pi pi-exclamation-triangle"></i> {{ t('troubleshooting.generation.badQuality') }}</h4>
              <p>{{ t('troubleshooting.generation.badQualitySolution') }}</p>
            </div>
          </section>

          <!-- Footer -->
          <footer class="docs-footer">
            <Divider />
            <div class="footer-content">
              <span>{{ t('version') }}: v1.0.0</span>
              <span>Green Deck - MIT License</span>
              <a href="https://github.com/Erick-Bryan-Cubas/green-deck" target="_blank">
                <i class="pi pi-github"></i> GitHub
              </a>
            </div>
          </footer>
        </ScrollPanel>
      </main>
    </div>
  </div>
</template>

<style scoped>
.docs-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
}

.docs-toolbar {
  background: rgba(15, 23, 42, 0.95);
  backdrop-filter: blur(12px);
  border: none;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  padding: 0.75rem 1.5rem;
  position: sticky;
  top: 0;
  z-index: 100;
}

.toolbar-start {
  display: flex;
  align-items: center;
  gap: 12px;
}

.docs-logo {
  width: 32px;
  height: 32px;
  filter: drop-shadow(0 2px 4px rgba(16, 185, 129, 0.3));
}

.docs-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #fff;
  letter-spacing: -0.02em;
}

.toolbar-center {
  display: flex;
  justify-content: center;
}

.search-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 12px;
  color: rgba(255, 255, 255, 0.4);
  font-size: 0.9rem;
  pointer-events: none;
  z-index: 1;
}

.docs-search {
  width: 300px;
  padding-left: 36px !important;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 8px;
  color: #fff;
}

.docs-search::placeholder {
  color: rgba(255, 255, 255, 0.4);
}

.docs-search:focus {
  border-color: #10b981;
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
}

.docs-search:focus + .search-icon,
.search-wrapper:focus-within .search-icon {
  color: #10b981;
}

.toolbar-end {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lang-selector {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
}

.lang-selector :deep(.p-button) {
  padding: 0.5rem 0.75rem;
  font-size: 0.8rem;
}

.docs-container {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* Sidebar */
.docs-sidebar {
  width: 280px;
  min-width: 280px;
  background: rgba(15, 23, 42, 0.8);
  border-right: 1px solid rgba(148, 163, 184, 0.1);
  display: flex;
  flex-direction: column;
  position: relative;
  transition: all 0.3s ease;
}

.docs-sidebar.collapsed {
  width: 0;
  min-width: 0;
  overflow: hidden;
}

.sidebar-toggle-btn {
  position: absolute;
  right: -16px;
  top: 20px;
  z-index: 10;
  width: 32px;
  height: 32px;
  background: rgba(30, 41, 59, 0.95) !important;
  border: 1px solid rgba(148, 163, 184, 0.2) !important;
  border-radius: 50% !important;
}

.sidebar-scroll {
  flex: 1;
  height: calc(100vh - 70px);
}

.docs-tree {
  padding: 1rem;
  background: transparent;
}

.docs-tree :deep(.p-tree-node-content) {
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  transition: all 0.2s ease;
  gap: 8px;
}

.docs-tree :deep(.p-tree-node-content:hover) {
  background: rgba(99, 102, 241, 0.1);
}

.docs-tree :deep(.p-tree-node-icon) {
  color: rgba(255, 255, 255, 0.6);
  font-size: 0.95rem;
}

.docs-tree :deep(.p-tree-node-content:hover .p-tree-node-icon) {
  color: #6366f1;
}

.docs-tree :deep(.p-tree-toggler) {
  color: rgba(255, 255, 255, 0.4);
  width: 1.5rem;
  height: 1.5rem;
}

.docs-tree :deep(.p-tree-toggler:hover) {
  background: rgba(99, 102, 241, 0.15);
  color: #fff;
}

.tree-label {
  color: rgba(255, 255, 255, 0.8);
  font-size: 0.9rem;
  transition: color 0.2s ease;
}

.tree-label.active {
  color: #10b981;
  font-weight: 600;
}

/* Content */
.docs-content {
  flex: 1;
  overflow: hidden;
}

.content-scroll {
  height: calc(100vh - 70px);
  padding: 2rem 3rem;
}

.doc-section {
  max-width: 900px;
  margin: 0 auto;
  color: rgba(255, 255, 255, 0.9);
}

.doc-section h1 {
  font-size: 2rem;
  font-weight: 700;
  color: #fff;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 12px;
}

.doc-section h1 i {
  color: #10b981;
}

.doc-section h2 {
  font-size: 1.4rem;
  font-weight: 600;
  color: #fff;
  margin-top: 2rem;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 10px;
}

.doc-section h2 i {
  color: #6366f1;
  font-size: 1.1rem;
}

.doc-section h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
}

.doc-section h4 {
  font-size: 1rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.85);
  margin-bottom: 0.5rem;
  margin-top: 1rem;
  display: flex;
  align-items: center;
  gap: 8px;
}

.option-tag {
  font-size: 0.75rem;
  padding: 0.15rem 0.5rem;
  font-weight: 700;
}

.subtitle {
  font-size: 1.1rem;
  color: #10b981;
  font-weight: 500;
  margin-bottom: 1rem;
}

.description {
  font-size: 1rem;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.75);
}

/* Lists */
.feature-list,
.requirements-list,
.stack-list,
.steps-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.feature-list li,
.requirements-list li,
.stack-list li {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 0.75rem 0;
  color: rgba(255, 255, 255, 0.8);
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
}

.feature-list li i,
.requirements-list li i {
  color: #10b981;
  margin-top: 2px;
}

.steps-list {
  padding-left: 1.5rem;
}

.steps-list li {
  padding: 0.5rem 0;
  color: rgba(255, 255, 255, 0.8);
}

.card-types-list {
  list-style: none;
  padding: 0;
}

.card-types-list li {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  margin-bottom: 0.5rem;
  color: rgba(255, 255, 255, 0.8);
}

/* Code Blocks */
.code-block {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 12px;
  overflow: hidden;
  margin: 1rem 0;
}

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem;
  background: rgba(255, 255, 255, 0.05);
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.code-header span {
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.5);
  font-weight: 600;
  text-transform: uppercase;
}

.code-block pre {
  margin: 0;
  padding: 1rem;
  overflow-x: auto;
}

.code-block code {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 0.85rem;
  color: #e2e8f0;
  line-height: 1.6;
}

/* Tables */
.syntax-table,
.api-table {
  margin-top: 1rem;
}

.syntax-table :deep(.p-datatable-table),
.api-table :deep(.p-datatable-table) {
  background: rgba(0, 0, 0, 0.2);
}

.syntax-code,
.endpoint-code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  background: rgba(99, 102, 241, 0.15);
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  color: #a5b4fc;
}

/* Status indicators */
.status-list {
  list-style: none;
  padding: 0;
}

.status-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0.5rem 0;
  color: rgba(255, 255, 255, 0.8);
}

.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.status-dot.green {
  background: #10b981;
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.5);
}

.status-dot.red {
  background: #ef4444;
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.5);
}

/* FAQ */
.faq-list {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.faq-item {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 12px;
  padding: 1.5rem;
}

.faq-item h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #fff;
  margin: 0 0 0.75rem 0;
}

.faq-item h3 i {
  color: #6366f1;
}

.faq-item p {
  color: rgba(255, 255, 255, 0.7);
  margin: 0;
  line-height: 1.6;
}

/* Troubleshooting */
.troubleshoot-item {
  background: rgba(239, 68, 68, 0.05);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: 12px;
  padding: 1.25rem;
  margin-bottom: 1rem;
}

.troubleshoot-item h4 {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #fca5a5;
  margin: 0 0 0.5rem 0;
}

.troubleshoot-item h4 i {
  color: #ef4444;
}

.troubleshoot-item p {
  color: rgba(255, 255, 255, 0.7);
  margin: 0;
  line-height: 1.6;
}

/* Endpoint examples */
.endpoint-example {
  margin-bottom: 2rem;
}

.endpoint-example h3 {
  display: flex;
  align-items: center;
  gap: 10px;
}

.method-tag {
  font-size: 0.75rem;
}

/* Footer */
.docs-footer {
  margin-top: 3rem;
  padding-bottom: 2rem;
}

.footer-content {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 2rem;
  color: rgba(255, 255, 255, 0.4);
  font-size: 0.85rem;
}

.footer-content a {
  color: rgba(255, 255, 255, 0.5);
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: color 0.2s ease;
}

.footer-content a:hover {
  color: #10b981;
}

/* Responsive */
@media (max-width: 1024px) {
  .docs-sidebar {
    position: fixed;
    left: 0;
    top: 70px;
    bottom: 0;
    z-index: 50;
    background: rgba(15, 23, 42, 0.98);
  }

  .docs-sidebar.collapsed {
    left: -280px;
  }

  .content-scroll {
    padding: 1.5rem;
  }
}

@media (max-width: 768px) {
  .toolbar-center {
    display: none;
  }

  .docs-search {
    width: 100%;
  }

  .doc-section h1 {
    font-size: 1.5rem;
  }

  .doc-section h2 {
    font-size: 1.2rem;
  }

  .content-scroll {
    padding: 1rem;
  }
}
</style>
