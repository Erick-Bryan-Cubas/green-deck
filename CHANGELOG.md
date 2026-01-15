# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

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
