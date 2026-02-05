# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.3.0-beta] - 2026-02-05

### Adicionado

- **Seletor de tipo de cartão**
  - Interface para escolher entre tipos de cartão (Basic, Cloze, Mixed)
  - Estilos visuais de CTA em verde

- **WebSocket Extraction Manager**
  - Gerenciador de extração via WebSocket
  - Indicador de progresso na UI durante extração

- **Suporte a temas**
  - Sistema de theming com CSS variables
  - Refatoração para variáveis CSS centralizadas

- **Zen Mode**
  - Modo de leitura imersivo (Zen mode switch)
  - Controles reorganizados na interface

- **Melhorias em PDF**
  - Endpoint de thumbnails para PDFs
  - Endpoint rápido de metadados PDF
  - Performance de preview melhorada
  - Feedback de progresso aprimorado

- **Extração de documentos**
  - Timeouts configuráveis para extração
  - Streaming de progresso durante extração

- **Geração AllInOne**
  - Suporte a geração de questões AllInOne
  - Parsing de features avançadas

### Segurança

- **Headers de segurança aprimorados**
  - Atualização da função de hash
  - Headers mais robustos

### Alterado

- Layout do header refinado
- CSS responsivo melhorado
- Filtros de logging aprimorados
- Documentação Docker atualizada

---

## [1.2.0-beta] - 2026-01-23

### Adicionado

- **Suporte completo a Docker (deploy e operação)**
  - Adicionado `.dockerignore` para otimizar builds (menos lixo no contexto, imagem menor e build mais rápido)
  - README (EN/PT) expandido com passo a passo de deploy via Docker, configuração, troubleshooting e **persistência de dados**
  - `.env.example` estendido com variáveis específicas para Docker, persistência e seções anotadas para facilitar setup (local vs Docker)

- **Rate limiting em endpoints críticos da API**
  - Limitação de requisições aplicada aos principais endpoints com middleware `limiter`

- **Melhorias na API**
  - `CardsRequest` agora suporta flag `isExamMode` para geração de simulado/prova

### Alterado

- **Tratamento de API Keys mais seguro**
  - Endpoints passam a extrair API keys preferencialmente dos **headers** (mantendo compatibilidade com envio no body)
  - Lógica de merge/normalização de chaves ajustada para suportar os dois formatos

- **Documentação reorganizada e aprofundada (EN/PT)**
  - Instruções mais detalhadas para configuração, execução, persistência e diagnóstico de problemas

### Segurança

- **API Keys agora são tratadas de forma mais segura**
  - Extração preferencial via **headers** (em vez de body), reduzindo risco de:
    - chaves aparecerem em logs de payload
    - chaves vazarem em traces de erro, tools de debug, proxies e histórico de requests
  - Mantida **retrocompatibilidade** com o formato antigo (body), evitando quebrar integrações existentes
  - Normalização/merge de chaves aprimorado para lidar corretamente com múltiplas origens (headers + body), priorizando o caminho mais seguro

- **Rate limiting em endpoints sensíveis**
  - Aplicação de limites de requisições em rotas críticas para reduzir:
    - brute force / abuso de endpoints
    - exaustão de recursos (CPU/GPU/LLM calls) por uso malicioso ou acidental
    - custos inesperados em provedores pagos
  - Integração via middleware `limiter` com regras específicas por endpoint (quando aplicável)

- **Validação e logging mais “safe-by-default”**
  - Regras de validação reforçadas para inputs/prompt (incluindo sanitização/checagens extras)
  - Logging ajustado para melhorar rastreabilidade **sem** expor conteúdo sensível (como credenciais e dados de configuração)

- **Configuração de segurança mais explícita**
  - `.env.example` ampliado com seções anotadas para:
    - variáveis relacionadas a segurança e rate limiting
    - parâmetros específicos de execução em Docker (reduzindo configurações “soltas” e inconsistentes entre ambientes)

---

## [1.0.1-beta] - 2026-01-16

### Adicionado

- **Suporte a pdfplumber para extração de PDF**
  - Nova opção de extração com pdfplumber como alternativa ao Docling
  - Seleção de páginas específicas para extração
  - Melhor performance em PDFs simples

- **Autocompletar e edição de tags do Anki**
  - Autocomplete de tags existentes ao adicionar cartões
  - Suporte a edição de tags em cartões existentes

- **Componentes de modal separados**
  - `AnkiExportDialog.vue` - Diálogo de exportação para Anki redesenhado
  - `ApiKeysDialog.vue` - Gerenciamento de chaves de API
  - `CustomInstructionDialog.vue` - Instruções personalizadas
  - `EditCardDialog.vue` - Edição de cartões com Quill editor
  - `GenerateModal.vue` - Modal de geração de cartões
  - `IntroModal.vue` - Modal de introdução
  - `ModelSelectionDialog.vue` - Seleção de modelos LLM
  - `OllamaSelectionDialog.vue` - Seleção de modelos Ollama
  - `ProgressDialog.vue` - Progresso de operações
  - `PromptSettingsDialog.vue` - Configurações de prompts
  - `TopicConfirmDialog.vue` - Confirmação de tópicos

### Alterado

- Atualizado sistema de versionamento para indicar estágio beta
- Adicionado badge visual "BETA" na interface (sidebar)
- Centralizada configuração de versão no frontend (`frontend/src/config/version.ts`)
- Sincronizada versão em todos os arquivos de configuração (pyproject.toml, package.json, app/__init__.py, app/main.py, run.py)
- Renomeado app para "green-deck" em todos os arquivos de configuração
- Removidos arquivos package.json e package-lock.json da raiz (movidos para frontend/)
- Atualizadas dependências do frontend
- Refatorado `GeneratorPage.vue` para usar componentes de modal dedicados (redução significativa de código)
- Refatorado `EditCardDialog` para usar Quill editor com melhor UI
- Redesenhado modal de exportação Anki com UI melhorada e localização

### Corrigido

- Corrigido estado expandido do sidebar nas páginas
- Melhorado tratamento de erros e feedback na exportação para Anki

---

## [1.0.0] - 2026-01-15

### Adicionado

#### Geração de Flashcards com IA

- **Suporte a múltiplos provedores LLM**
  - Ollama (local, gratuito, offline)
  - OpenAI (GPT-4, GPT-3.5)
  - Perplexity (modelos Sonar)
  - Fallback dinâmico entre modelos com auto-detecção
- **Tipos de cartões**
  - Cartões Básicos (formato Q&A)
  - Cartões Cloze com múltiplos blanks (`{{c1::}}`, `{{c2::}}`, etc.)
  - Modo misto (Basic + Cloze para cada conceito)
- **Pipeline de qualidade**
  - Validação de fonte (garante correspondência com texto original)
  - Filtragem por relevância de conteúdo
  - Algoritmo de pontuação de qualidade
  - Validação baseada em LLM
  - Injeção de checklist SuperMemo 20 para alta retenção
- **Operações avançadas**
  - Reescrita de cartões (densificar, simplificar, dividir)
  - Níveis de dificuldade (fácil, neutro/difícil, técnico/difícil)
  - Prompts configuráveis (sistema, geração, diretrizes)
  - Suporte a tipos de nota personalizados

#### Análise de Texto e Segmentação

- **Chunking semântico**
  - Segmentação inteligente usando embeddings
  - Chunking baseado em sentenças com overlap
  - Tokenização NLTK com suporte a idiomas
  - Tamanhos de chunk e overlap configuráveis
- **Segmentação de tópicos (LangExtract)**
  - Detecção automática de definições, exemplos, conceitos, fórmulas, procedimentos e comparações
  - Destaque visual com overlays coloridos
  - Suporte a exemplos few-shot
- **Modos de análise**
  - Análise baseada em embeddings
  - Análise baseada em LLM
  - Modo automático (seleção inteligente)

#### Processamento de Documentos

- **Formatos suportados** (via Docling)
  - Arquivos PDF
  - Microsoft Office (Word, PowerPoint, Excel)
  - Markup (HTML, Markdown, AsciiDoc)
  - Imagens com OCR (PNG, JPG, TIFF, BMP)
- **Funcionalidades**
  - Seleção e preview de páginas
  - Níveis de qualidade de extração (raw, limpo, refinado por LLM)
  - Suporte a documentos multi-página
  - Preservação de metadados
  - Contagem de palavras

#### Integração com Anki

- **Gerenciamento de decks**
  - Listar todos os decks disponíveis
  - Criar novos decks
  - Suporte a múltiplos decks
  - Estatísticas e analytics por deck
- **Operações com cartões**
  - Adicionar cartões aos decks
  - Atualizar cartões existentes
  - Suspender/reativar cartões
  - Operações em lote
  - Validação de campos
- **Gerenciamento de tipos de nota**
  - Listar tipos de nota disponíveis
  - Migração de campos (mover conteúdo entre layouts)
  - Suporte a tipos de nota personalizados
- **Tradução de cartões**
  - Traduzir cartões usando LLM
  - Detecção automática de idioma

#### Dashboard e Analytics

- **Estatísticas em tempo real**
  - Métricas de geração de cartões
  - Tracking de performance por deck
  - Estatísticas de estudo (novos, aprendendo, revisão, pendentes, suspensos)
  - Filtro por deck
- **Visualizações**
  - Gráficos e KPIs animados
  - Distribuição de cartões por deck
  - Estatísticas diárias e análise de tendências
  - Segmentação KMeans para clustering de decks
- **Histórico**
  - Navegação por análises passadas
  - Visualização do histórico de cartões gerados

#### Interface do Usuário

- **Página Generator**
  - Editor de texto rico (Quill Editor) com formatação
  - Destaque de tópicos em tempo real
  - Modo de leitura imersivo (estilo Kindle)
  - Suporte a visualização em duas páginas
  - Escala de fonte e opções de tema
  - Números de linha no editor
  - Tracking de progresso
- **Página Dashboard**
  - Visualização abrangente de estatísticas
  - Filtro por intervalo de datas
  - KPIs com números animados
  - Tabela de dados com paginação
  - Diálogos de detalhes por deck e por dia
- **Página Browser**
  - Navegação por cartões gerados
  - Filtro e busca
  - Capacidade de edição de cartões
- **Componentes**
  - Widget de upload de documentos
  - Upload e preview de PDF
  - Editor Quill com lazy loading
  - Indicador de status do Anki
  - Indicador de status do Ollama
  - Diálogo de edição de prompts
  - Overlay de legenda de tópicos

#### Streaming e Tempo Real

- **Conectividade WebSocket**
  - Atualizações de status do Anki em tempo real
  - Monitoramento de conexão do Ollama
  - Relatório de uso de GPU/VRAM
  - Polling periódico (intervalos de 3 segundos)
  - Mecanismo keep-alive ping/pong
- **Server-Sent Events (SSE)**
  - Geração de cartões com streaming
  - Atualizações de progresso em tempo real
  - Tracking de estágios do pipeline
  - Análise de texto com streaming

#### Cache e Performance

- **Cache de embeddings**
  - Cache em memória para embeddings
  - Suporte a embeddings em lote
  - Endpoint de estatísticas de cache
  - Cálculos de similaridade coseno
- **Cache de respostas LLM**
  - Cache baseado em prompts
  - Cache específico por provedor
- **Cache de provedores de modelo**
  - TTL de 5 minutos para listas de modelos
  - Suporte a Ollama, OpenAI, Perplexity, Anthropic
  - Detecção automática de modelos

#### Configuração

- **Variáveis de ambiente**
  - `OLLAMA_HOST` - URL do servidor Ollama
  - `OLLAMA_MODEL` - Modelo de geração (auto-detectado se não definido)
  - `OLLAMA_ANALYSIS_MODEL` - Modelo de análise/embedding
  - `OLLAMA_VALIDATION_MODEL` - Modelo de validação de qualidade
  - `ANKI_CONNECT_URL` - URL do AnkiConnect
  - `PORT` - Porta do servidor
- **Gerenciamento de API Keys**
  - Persistência de chaves via LocalStorage
  - Suporte a chaves OpenAI, Perplexity, Anthropic

#### API REST Completa

- **Geração**: `/api/generate-cards-stream`, `/api/analyze-text-stream`, `/api/segment-topics`, `/api/rewrite-card`
- **Documentos**: `/api/documents/extract`, `/api/documents/preview-pages`, `/api/documents/extract-pages`
- **Anki**: `/api/anki-decks`, `/api/anki-models`, `/api/upload-to-anki`, `/api/anki-translate`, `/api/anki-migrate-fields`
- **Dashboard**: `/api/dashboard/summary`, `/api/dashboard/by-day`, `/api/dashboard/top-decks`, `/api/dashboard/segments`
- **Histórico**: `/api/history/analyses`, `/api/history/cards`, `/api/history/stats`
- **Status**: `/api/health`, `/api/anki-status`, `/api/ollama-status`, `/api/ollama-info`

#### Persistência de Dados

- Banco de dados DuckDB (serverless SQL)
- Tabelas: `analyses`, `cards`, `llm_responses`, `generation_requests`, `filter_results`, `pipeline_stages`
- Auto-inicialização na primeira execução

#### Stack Técnico

- **Backend**: FastAPI, Uvicorn, Python 3.12+
- **Frontend**: Vue 3, Vite, PrimeVue, Chart.js
- **ML/AI**: NLTK, scikit-learn, PyTorch, Docling
- **Qualidade**: Ruff, pytest, pytest-asyncio

---

## Links

- [Repositório](https://github.com/Erick-Bryan-Cubas/green-deck)
- [Anki](https://apps.ankiweb.net/)
- [AnkiConnect](https://ankiweb.net/shared/info/2055492159)
- [Ollama](https://ollama.ai/)
