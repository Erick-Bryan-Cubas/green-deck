<p align="center">
  <img src="frontend/public/green.svg" alt="Green Deck Logo" width="120" height="120">
</p>

<h1 align="center">Green Deck</h1>

<p align="center">
  <strong>AI-Powered Intelligent Flashcard Generator</strong>
</p>

<p align="center">
  <a href="#english">English</a> •
  <a href="#português">Português</a>
</p>

<p align="center">
  <strong>Deploy Docker:</strong>
  <a href="#docker-deploy-en">EN</a> •
  <a href="#docker-deploy-pt">PT</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Vue.js-3-42B883?logo=vuedotjs&logoColor=white" alt="Vue.js">
  <img src="https://img.shields.io/badge/FastAPI-00C7B7?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Docker-0DB7ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/DuckDB-FFD600?logo=duckdb&logoColor=black" alt="DuckDB">
  <img src="https://img.shields.io/badge/AnkiConnect-FF6F00?logo=anki&logoColor=white" alt="AnkiConnect">
  <img src="https://img.shields.io/badge/Docling%20(OCR)-FF4081?logo=tesseract&logoColor=white" alt="Docling OCR">
  <img src="https://img.shields.io/badge/Ollama-LLM_Local-7C3AED?logo=ollama&logoColor=white" alt="Ollama">
  <img src="https://img.shields.io/badge/License-MIT-22C55E" alt="License">
</p>

---

# English

## Overview

Green Deck is an open-source AI-powered flashcard generator that automatically creates high-quality study cards from text, PDFs, and documents. It integrates seamlessly with **Anki** for spaced repetition learning and supports multiple LLM providers including local models via **Ollama**.

### Why Green Deck?

- **Smart Generation**: Uses LLMs to create both Basic and Cloze deletion cards
- **Quality Filtering**: Multi-stage pipeline ensures only high-quality cards reach your deck
- **Local-First**: Run entirely offline with Ollama, or use cloud providers (OpenAI, Perplexity)
- **Direct Anki Sync**: Upload cards directly to Anki without manual import/export
- **Document Support**: Extract text from PDFs, Word, PowerPoint, Excel, and images (OCR)

## Features

### Flashcard Generation
- **Multiple Card Types**: Basic (Q&A) and Cloze deletion (`{{c1::answer}}`)
- **Multi-Provider LLM Support**:
  - Ollama (local, free)
  - OpenAI (GPT-4, GPT-3.5)
  - Perplexity (Sonar models)
- **Quality Pipeline**:
  - Source validation (ensures cards match source text)
  - Content relevance filtering
  - Quality scoring algorithm
  - Language detection (PT, EN, ES)
- **Card Rewriting**: Densify, simplify, or split cards with AI assistance

### Text Analysis
- **Semantic Chunking**: Intelligent text segmentation using embeddings
- **Topic Segmentation**: Automatic detection of definitions, examples, concepts, formulas, procedures, and comparisons
- **Visual Highlighting**: Color-coded topic overlay in the editor

### Document Processing
- **Supported Formats**:
  - PDF files
  - Microsoft Office (Word, PowerPoint, Excel)
  - Markup (HTML, Markdown, AsciiDoc)
  - Images with OCR (PNG, JPG, TIFF, BMP)
- **Page Selection**: Preview and extract specific pages
- **Quality Levels**: Raw, cleaned, or LLM-refined extraction

### Anki Integration
- **Deck Management**: List, create, and manage decks
- **Card Operations**: Add, update, suspend, and bulk-select cards
- **Field Migration**: Safely move content between note type layouts
- **Card Translation**: Translate cards using LLM with language detection

### Dashboard & Analytics
- **Real-Time Statistics**: Card generation metrics and deck performance
- **Visualizations**: Charts, KPIs, and trend analysis
- **History Tracking**: Browse past analyses and generated cards

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | FastAPI, Python 3.11+, Uvicorn |
| **Frontend** | Vue 3, Vite, PrimeVue, Quill Editor |
| **Database** | DuckDB (serverless SQL) |
| **AI/ML** | Ollama, OpenAI API, Perplexity API |
| **Document Processing** | Docling (multi-format extraction) |
| **Anki Bridge** | AnkiConnect |

## Installation

### Prerequisites

- Python 3.11+
- Node.js 20+ (recommended: use [nvm](https://github.com/nvm-sh/nvm))
- [Ollama](https://ollama.ai/) (for local LLM)
- [Anki](https://apps.ankiweb.net/) with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) addon

<a id="docker-deploy-en"></a>

### Quick Start (Recommended: Docker)

```bash
# 1. Clone the repository
git clone https://github.com/Erick-Bryan-Cubas/green-deck.git
cd green-deck

# 2. Copy and configure environment
cp .env.example .env
# Edit .env as needed (see Docker configuration below)

# 3. Build and run
docker compose -p green-deck -f docker/docker-compose.yml up -d --build

# 4. View logs
docker compose -p green-deck -f docker/docker-compose.yml logs -f green-deck
```

The application will be available at `http://localhost:3000`

### Local Development (frontend first)

```bash
# 1. Clone the repository
git clone https://github.com/Erick-Bryan-Cubas/green-deck.git
cd green-deck

# 2. Install frontend dependencies and build (required before backend in local mode)
cd frontend
npm install
npm run build
cd ..

# 3. Create and activate virtual environment
python3 -m venv srs-venv
source srs-venv/bin/activate  # Linux/macOS
# or
.\srs-venv\Scripts\activate  # Windows

# Install Python dependencies 
## 4. 1. PIP
pip install -r requirements.txt
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

## Poetry (optional)
sudo apt install python3-poetry # Linux
# or
pipx install poetry # Windows

poetry add fastapi "uvicorn[standard]>=0.32.0" httpx python-dotenv numpy langid duckdb python-multipart
poetry add --group dev ruff pytest pytest-asyncio
poetry source add --priority=explicit pytorch-cu124 https://download.pytorch.org/whl/cu124
poetry add --source pytorch-cu124 torch torchvision torchaudio
poetry install

# 5. Start the application
python run.py

## with Poetry
poetry run python run.py
# Or
poetry self add poetry-plugin-shell
poetry shell
python run.py
```

The application will be available at `http://localhost:3000`

## Docker Deployment (recommended)

### Docker Configuration

When running in Docker, configure these variables in your `.env` file:

| Variable | Docker Value | Description |
|----------|--------------|-------------|
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Access Ollama on host machine |
| `ANKI_CONNECT_URL` | `http://host.docker.internal:8765` | Access Anki on host machine |
| `ENVIRONMENT` | `production` | Set to production for Docker |

### Document Processing Configuration

Green Deck supports extracting text from various document formats (PDF, DOCX, PPTX, etc.) with configurable timeout limits for large files. You can adjust these timeouts in your `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCUMENT_EXTRACTION_TIMEOUT` | `180` | Maximum time (seconds) for full document extraction (3 minutes) |
| `DOCUMENT_PREVIEW_TIMEOUT` | `90` | Maximum time (seconds) for document preview (90 seconds) |

**Recommendations:**
- Small deployments (personal use): 120-180 seconds
- Medium deployments (team use): 180-240 seconds
- Large files (100+ pages): 300 seconds or use page selection

**Tips for large files:**
1. Select specific pages instead of extracting the entire document
2. Use the "pdfplumber" extractor (faster but less formatting)
3. Split large documents into smaller files

**Real-time Progress:** When extracting documents, you'll see a real-time progress bar showing:
- Percentage complete (e.g., "45%")
- Current status (e.g., "Processing page 23 of 150...")
- Cancel button to abort long-running extractions

### Running with Ollama Container

To run Ollama as a Docker container alongside Green Deck:

```bash
  docker compose -p green-deck -f docker/docker-compose.yml -f docker/docker-compose.ollama.yml up -d
```

Then pull your models:
```bash
docker exec ollama ollama pull qwen2.5:7b
docker exec ollama ollama pull nomic-embed-text
```

### Development with Docker

For development with hot-reload:

```bash
docker compose -p green-deck -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d
```

This mounts your local `app/` directory for live code changes.

### Rebuilding After Updates

After pulling new changes or modifying the code, rebuild the containers to apply updates:

```bash
# Rebuild and restart all containers
docker compose -p green-deck -f docker/docker-compose.yml up -d --build

# Or rebuild a specific service
docker compose -p green-deck -f docker/docker-compose.yml build green-deck
docker compose -p green-deck -f docker/docker-compose.yml up -d green-deck

# Force rebuild without cache (useful for major updates)
docker compose -p green-deck -f docker/docker-compose.yml build --no-cache
docker compose -p green-deck -f docker/docker-compose.yml up -d
```

### Data Persistence

Docker volumes are used to persist data:
- `green-deck-data`: DuckDB database and generated files

To backup your data:
```bash
docker run --rm -v green-deck-data:/data -v $(pwd):/backup alpine tar czf /backup/green-deck-backup.tar.gz /data
```

### Docker Troubleshooting

**Cannot connect to Ollama:**
- Ensure Ollama is running on your host machine
- On Linux, the `extra_hosts` config in `docker/docker-compose.yml` handles `host.docker.internal`
- Check firewall settings allow connections from Docker

**Cannot connect to Anki:**
- Ensure Anki is running with AnkiConnect addon installed
- AnkiConnect must be configured to accept connections from Docker's IP range

**GPU not detected:**
- Ensure NVIDIA Container Toolkit is installed
- Verify with: `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`

---

### Ollama Setup

```bash
# Pull the models you want to use
# Check available models at https://ollama.ai/library

# (Optional) Create custom flashcard model
ollama create qwen-flashcard -f models/qwen_flashcard_finetuned/Modelfile
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Generation model | `qwen-flashcard` |
| `OLLAMA_ANALYSIS_MODEL` | Analysis/embedding model | `nomic-embed-text` |
| `ANKI_CONNECT_URL` | AnkiConnect URL | `http://localhost:8765` |
| `PORT` | Server port | `3000` |

## Usage

### Basic Workflow

1. **Input Text**: Paste or type text in the editor, or upload a document
2. **Analyze**: Click "Analyze" to segment text into topics
3. **Generate**: Select text and click "Generate Cards"
4. **Review**: Preview generated cards and filter as needed
5. **Export**: Upload directly to Anki or copy to clipboard

### Using Cloud Providers

Add your API keys in the settings panel:
- **OpenAI**: Enter your API key for GPT-4/GPT-3.5 access
- **Perplexity**: Enter your API key for Sonar model access

## API Reference

Base URL: `http://localhost:3000`  
OpenAPI docs: `http://localhost:3000/docs`

### Health & Status
- `GET /api/health`
- `GET /api/cache-stats`
- `GET /api/anki-status`
- `GET /api/ollama-status`
- `GET /api/ollama-info`
- `GET /api/health/anki`
- `GET /api/health/ollama`

### Flashcards
- `POST /api/generate-cards-stream`
- `POST /api/analyze-text-stream`
- `POST /api/segment-topics`
- `GET /api/prompts/defaults`
- `POST /api/generate-cards-cancel/{request_id}`
- `POST /api/rewrite-card`

### Questions
- `POST /api/generate-questions-stream`
- `POST /api/parse-questions-stream`
- `GET /api/question-prompts`

### Documents
- `GET /api/documents/status`
- `POST /api/documents/pdf-metadata`
- `POST /api/documents/pdf-thumbnails`
- `POST /api/documents/extract`
- `POST /api/documents/extract-and-preview`
- `POST /api/documents/preview-pages`
- `POST /api/documents/extract-pages`
- `POST /api/documents/extract-stream`
- `POST /api/documents/extract-pages-stream`
- `POST /api/documents/extract-pages-async`
- `POST /api/documents/extract-cancel/{task_id}`

### Anki
- `POST /api/upload-to-anki`
- `GET /api/anki-decks`
- `GET /api/anki-models`
- `GET /api/anki-tags`
- `GET /api/anki-note-types`
- `GET /api/anki-cards`
- `POST /api/anki-recreate`
- `POST /api/anki-note-suspend`
- `GET /api/anki-note-info`
- `POST /api/anki-note-update`
- `POST /api/anki-migrate-fields`
- `POST /api/anki-translate`
- `POST /api/detect-card-languages`
- `POST /api/upload-questions-to-anki`
- `GET /api/check-allinone-model`

### Dashboard
- `GET /api/dashboard/summary`
- `GET /api/dashboard/reviews-by-day`
- `GET /api/dashboard/study-time-by-day`
- `GET /api/dashboard/success-rate-by-day`
- `GET /api/dashboard/top-decks`
- `GET /api/dashboard/segments`

### History
- `GET /api/history/analyses`
- `GET /api/history/cards`
- `GET /api/history/stats`

### Models
- `GET /api/all-models`

### WebSocket
- `WS /ws/status`
- `WS /ws/extraction`

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

# Português

## Visão Geral

Green Deck é um gerador de flashcards open-source com inteligência artificial que cria automaticamente cartões de estudo de alta qualidade a partir de texto, PDFs e documentos. Integra-se perfeitamente com o **Anki** para aprendizado por repetição espaçada e suporta múltiplos provedores de LLM, incluindo modelos locais via **Ollama**.

### Por que Green Deck?

- **Geração Inteligente**: Usa LLMs para criar cartões Básicos e Cloze
- **Filtragem de Qualidade**: Pipeline multi-estágio garante que apenas cartões de alta qualidade cheguem ao seu deck
- **Local-First**: Execute totalmente offline com Ollama, ou use provedores cloud (OpenAI, Perplexity)
- **Sincronização Direta com Anki**: Envie cartões diretamente para o Anki sem importação/exportação manual
- **Suporte a Documentos**: Extraia texto de PDFs, Word, PowerPoint, Excel e imagens (OCR)

## Funcionalidades

### Geração de Flashcards
- **Múltiplos Tipos de Cartão**: Básico (Pergunta/Resposta) e Cloze (`{{c1::resposta}}`)
- **Suporte Multi-Provedor LLM**:
  - Ollama (local, gratuito)
  - OpenAI (GPT-4, GPT-3.5)
  - Perplexity (modelos Sonar)
- **Pipeline de Qualidade**:
  - Validação de fonte (garante que cartões correspondam ao texto fonte)
  - Filtragem de relevância de conteúdo
  - Algoritmo de pontuação de qualidade
  - Detecção de idioma (PT, EN, ES)
- **Reescrita de Cartões**: Densifique, simplifique ou divida cartões com assistência de IA

### Análise de Texto
- **Chunking Semântico**: Segmentação inteligente de texto usando embeddings
- **Segmentação de Tópicos**: Detecção automática de definições, exemplos, conceitos, fórmulas, procedimentos e comparações
- **Destaque Visual**: Sobreposição de tópicos com cores no editor

### Processamento de Documentos
- **Formatos Suportados**:
  - Arquivos PDF
  - Microsoft Office (Word, PowerPoint, Excel)
  - Markup (HTML, Markdown, AsciiDoc)
  - Imagens com OCR (PNG, JPG, TIFF, BMP)
- **Seleção de Páginas**: Visualize e extraia páginas específicas
- **Níveis de Qualidade**: Extração bruta, limpa ou refinada por LLM

### Integração com Anki
- **Gerenciamento de Decks**: Liste, crie e gerencie decks
- **Operações com Cartões**: Adicione, atualize, suspenda e selecione cartões em massa
- **Migração de Campos**: Mova conteúdo entre layouts de tipos de nota com segurança
- **Tradução de Cartões**: Traduza cartões usando LLM com detecção de idioma

### Dashboard e Análises
- **Estatísticas em Tempo Real**: Métricas de geração de cartões e desempenho de decks
- **Visualizações**: Gráficos, KPIs e análise de tendências
- **Histórico**: Navegue por análises e cartões gerados anteriormente

## Stack Tecnológico

| Camada | Tecnologia |
|--------|------------|
| **Backend** | FastAPI, Python 3.11+, Uvicorn |
| **Frontend** | Vue 3, Vite, PrimeVue, Quill Editor |
| **Banco de Dados** | DuckDB (SQL serverless) |
| **IA/ML** | Ollama, OpenAI API, Perplexity API |
| **Processamento de Documentos** | Docling (extração multi-formato) |
| **Bridge Anki** | AnkiConnect |

## Instalação

### Pré-requisitos

- Python 3.11+
- Node.js 20+ (recomendado: use [nvm](https://github.com/nvm-sh/nvm))
- [Ollama](https://ollama.ai/) (para LLM local)
- [Anki](https://apps.ankiweb.net/) com addon [AnkiConnect](https://ankiweb.net/shared/info/2055492159)

<a id="docker-deploy-pt"></a>

### Início Rápido (Recomendado: Docker)

```bash
# 1. Clone o repositório
git clone https://github.com/Erick-Bryan-Cubas/green-deck.git
cd green-deck

# 2. Copie e configure o ambiente
cp .env.example .env
# Edite o .env conforme necessário (veja configuração Docker abaixo)

# 3. Build e execução
docker compose -f docker/docker-compose.yml up -d --build

# 4. Ver logs
docker compose -f docker/docker-compose.yml logs -f green-deck
```

A aplicação estará disponível em `http://localhost:3000`

### Desenvolvimento Local (frontend primeiro)

```bash
# 1. Clone o repositório
git clone https://github.com/Erick-Bryan-Cubas/green-deck.git
cd green-deck

# 2. Instale as dependências do frontend e faça o build (obrigatório antes do backend no modo local)
cd frontend
npm install
npm run build
cd ..

# 3. Crie e ative o ambiente virtual
python3 -m venv srs-venv
source srs-venv/bin/activate  # Linux/macOS
# ou
.\srs-venv\Scripts\activate  # Windows

# Instale as dependências Python 
## 4. 1. PIP
pip install -r requirements.txt
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

## Poetry (opcional)
sudo apt install python3-poetry # Linux
# ou
pipx install poetry # Windows

poetry add fastapi "uvicorn[standard]>=0.32.0" httpx python-dotenv numpy langid duckdb python-multipart
poetry add --group dev ruff pytest pytest-asyncio
poetry source add --priority=explicit pytorch-cu124 https://download.pytorch.org/whl/cu124
poetry add --source pytorch-cu124 torch torchvision torchaudio
poetry install

# 5. Inicie a aplicação
python run.py

## com Poetry
poetry run python run.py
# Ou
poetry self add poetry-plugin-shell
poetry shell
python run.py
```

A aplicação estará disponível em `http://localhost:3000`

## Deploy com Docker (recomendado)

### Configuração Docker

Ao rodar com Docker, configure estas variáveis no seu arquivo `.env`:

| Variável | Valor Docker | Descrição |
|----------|--------------|-----------|
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Acessa Ollama na máquina host |
| `ANKI_CONNECT_URL` | `http://host.docker.internal:8765` | Acessa Anki na máquina host |
| `ENVIRONMENT` | `production` | Define como produção para Docker |

### Executando com Container Ollama

Para rodar Ollama como container Docker junto com Green Deck:

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.ollama.yml up -d
```

Depois baixe seus modelos:
```bash
docker exec ollama ollama pull qwen2.5:7b
docker exec ollama ollama pull nomic-embed-text
```

### Desenvolvimento com Docker

Para desenvolvimento com hot-reload:

```bash
docker compose -p green-deck -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d
```

Isso monta seu diretório local `app/` para mudanças em tempo real.

### Reconstruir Após Atualizações

Após baixar novas mudanças ou modificar o código, reconstrua os containers para aplicar as atualizações:

```bash
# Reconstruir e reiniciar todos os containers
docker compose -p green-deck -f docker/docker-compose.yml up -d --build

# Ou reconstruir um serviço específico
docker compose -p green-deck -f docker/docker-compose.yml build green-deck
docker compose -p green-deck -f docker/docker-compose.yml up -d green-deck

# Forçar reconstrução sem cache (útil para atualizações maiores)
docker compose -p green-deck -f docker/docker-compose.yml build --no-cache
docker compose -p green-deck -f docker/docker-compose.yml up -d
```

### Persistência de Dados

Volumes Docker são usados para persistir dados:
- `green-deck-data`: Banco DuckDB e arquivos gerados

Para fazer backup dos dados:
```bash
docker run --rm -v green-deck-data:/data -v $(pwd):/backup alpine tar czf /backup/green-deck-backup.tar.gz /data
```

### Solução de Problemas Docker

**Não conecta ao Ollama:**
- Certifique-se que Ollama está rodando na máquina host
- No Linux, a config `extra_hosts` no `docker/docker-compose.yml` gerencia o `host.docker.internal`
- Verifique se o firewall permite conexões do Docker

**Não conecta ao Anki:**
- Certifique-se que Anki está rodando com addon AnkiConnect instalado
- AnkiConnect deve estar configurado para aceitar conexões da faixa IP do Docker

**GPU não detectada:**
- Certifique-se que NVIDIA Container Toolkit está instalado
- Verifique com: `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`

---

### Configuração do Ollama

```bash
# Baixe os modelos que deseja usar
# Confira os modelos disponíveis em https://ollama.ai/library

# (Opcional) Crie modelo personalizado para flashcards
ollama create qwen-flashcard -f models/qwen_flashcard_finetuned/Modelfile
```

### Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `OLLAMA_HOST` | URL do servidor Ollama | `http://localhost:11434` |
| `OLLAMA_MODEL` | Modelo de geração | `qwen-flashcard` |
| `OLLAMA_ANALYSIS_MODEL` | Modelo de análise/embedding | `nomic-embed-text` |
| `ANKI_CONNECT_URL` | URL do AnkiConnect | `http://localhost:8765` |
| `PORT` | Porta do servidor | `3000` |

## Como Usar

### Fluxo Básico

1. **Insira Texto**: Cole ou digite texto no editor, ou faça upload de um documento
2. **Analise**: Clique em "Analisar" para segmentar o texto em tópicos
3. **Gere**: Selecione o texto e clique em "Gerar Cartões"
4. **Revise**: Visualize os cartões gerados e filtre conforme necessário
5. **Exporte**: Envie diretamente para o Anki ou copie para a área de transferência

### Usando Provedores Cloud

Adicione suas chaves de API no painel de configurações:
- **OpenAI**: Insira sua chave de API para acesso ao GPT-4/GPT-3.5
- **Perplexity**: Insira sua chave de API para acesso aos modelos Sonar

## Referência da API

Base URL: `http://localhost:3000`  
Documentação OpenAPI: `http://localhost:3000/docs`

### Saúde e Status
- `GET /api/health`
- `GET /api/cache-stats`
- `GET /api/anki-status`
- `GET /api/ollama-status`
- `GET /api/ollama-info`
- `GET /api/health/anki`
- `GET /api/health/ollama`

### Flashcards
- `POST /api/generate-cards-stream`
- `POST /api/analyze-text-stream`
- `POST /api/segment-topics`
- `GET /api/prompts/defaults`
- `POST /api/generate-cards-cancel/{request_id}`
- `POST /api/rewrite-card`

### Questões
- `POST /api/generate-questions-stream`
- `POST /api/parse-questions-stream`
- `GET /api/question-prompts`

### Documentos
- `GET /api/documents/status`
- `POST /api/documents/pdf-metadata`
- `POST /api/documents/pdf-thumbnails`
- `POST /api/documents/extract`
- `POST /api/documents/extract-and-preview`
- `POST /api/documents/preview-pages`
- `POST /api/documents/extract-pages`
- `POST /api/documents/extract-stream`
- `POST /api/documents/extract-pages-stream`
- `POST /api/documents/extract-pages-async`
- `POST /api/documents/extract-cancel/{task_id}`

### Anki
- `POST /api/upload-to-anki`
- `GET /api/anki-decks`
- `GET /api/anki-models`
- `GET /api/anki-tags`
- `GET /api/anki-note-types`
- `GET /api/anki-cards`
- `POST /api/anki-recreate`
- `POST /api/anki-note-suspend`
- `GET /api/anki-note-info`
- `POST /api/anki-note-update`
- `POST /api/anki-migrate-fields`
- `POST /api/anki-translate`
- `POST /api/detect-card-languages`
- `POST /api/upload-questions-to-anki`
- `GET /api/check-allinone-model`

### Dashboard
- `GET /api/dashboard/summary`
- `GET /api/dashboard/reviews-by-day`
- `GET /api/dashboard/study-time-by-day`
- `GET /api/dashboard/success-rate-by-day`
- `GET /api/dashboard/top-decks`
- `GET /api/dashboard/segments`

### Histórico
- `GET /api/history/analyses`
- `GET /api/history/cards`
- `GET /api/history/stats`

### Modelos
- `GET /api/all-models`

### WebSocket
- `WS /ws/status`
- `WS /ws/extraction`

## Contribuindo

Contribuições são bem-vindas! Sinta-se à vontade para enviar um Pull Request.

1. Faça um fork do repositório
2. Crie sua branch de feature (`git checkout -b feature/recurso-incrivel`)
3. Faça commit das suas alterações (`git commit -m 'Adiciona recurso incrível'`)
4. Faça push para a branch (`git push origin feature/recurso-incrivel`)
5. Abra um Pull Request

## Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

---

<p align="center">
  Made with :green_heart: for the learning community
</p>
