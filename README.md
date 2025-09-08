# RAG com Gemini + Postgres (pgvector)

Projeto simples para ingestão de PDFs e perguntas usando Retrieval Augmented Generation (RAG) com embeddings de dimensão 3072 no Google Gemini e similaridade via `pgvector` no Postgres.

## Visão Geral

Fluxo:
1. Extrair texto de um PDF e quebrar em chunks.
2. Gerar embeddings (dimensão 3072) para cada chunk.
3. Armazenar `content` + `embedding` na tabela `documents` (vetor pgvector).
4. Para uma pergunta, gerar embedding da query, recuperar os `TOP_K` chunks mais similares e gerar resposta com o modelo generativo do Gemini.

## Requisitos

- Python 3.10+
- Docker (para subir Postgres rapidamente) ou Postgres local
- Chave de API do Google Gemini (`GEMINI_API_KEY`)

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edite a chave GEMINI_API_KEY
```

## Subindo Postgres com pgvector

Imagem (contém extensão pgvector):

```bash
docker run --name pg-rag \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_DB=ragdb \
  -p 5432:5432 \
  ankane/pgvector
```

Conecte e (opcionalmente) crie extensão/tabela manualmente (o projeto cria automaticamente se `AUTO_MIGRATE=1`):

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS documents (
  id SERIAL PRIMARY KEY,
  content TEXT NOT NULL,
  embedding VECTOR(3072) NOT NULL
);
-- (Opcional) índice para velocidade em busca aproximada
CREATE INDEX IF NOT EXISTS idx_documents_embedding ON documents USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);
```

## Configuração (.env)

Veja `.env.example`. Principais variáveis:

- `GEMINI_API_KEY`: chave obrigatória.
- `GEMINI_GENERATION_MODEL`: modelo de geração preferido (fallback para outros se falhar).
- `GEMINI_EMBEDDING_MODEL`: modelo de embedding (default `gemini-embedding-001`).
- `EMBEDDING_DIM`: dimensão de saída (3072).
- Conexão Postgres: usar `PG_DSN` ou componentes (`PG_HOST`, `PG_PORT`, etc.).
- `CHUNK_SIZE` / `CHUNK_OVERLAP`: controle de chunking.
- `TOP_K`: número de chunks recuperados.
- `MAX_CONTEXT_CHARS`: limite de caracteres agregados no contexto enviado ao modelo.
- `RETRY_MAX` / `RETRY_BASE_DELAY`: retry/backoff para geração.
- `AUTO_MIGRATE`: cria extensão/tabela/índice automaticamente (1 = ativo).

## Ingestão de PDF

```bash
python ingest.py apresentacao.pdf
```

O script:
1. Garante schema (se `AUTO_MIGRATE=1`).
2. Extrai texto.
3. Chunking.
4. Gera embedding 3072 para cada chunk.
5. Insere na tabela `documents`.

## Fazer Perguntas (RAG)

Interativo:
```bash
python ask.py
```

Pergunta única:
```bash
python ask.py "Qual o objetivo da apresentação?"
```

## Estrutura de Pastas

```
ask.py            # script de perguntas (RAG)
ingest.py         # script de ingestão de PDF
modules/
  config.py       # carregamento de variáveis e defaults
  db.py           # engine, migração e operações no banco
  embeddings.py   # cliente Gemini para embeddings
  pdf.py          # extração e chunking de PDFs
  rag.py          # pipeline RAG (busca + geração)
```

## Notas de Produção

- Ajuste `lists` do índice IVFFLAT conforme volume de dados.
- Considere normalizar texto (lowercase, limpeza) antes de embed.
- Para múltiplos PDFs, reexecute `ingest.py` apontando cada arquivo.
- Faça rotacionamento de chave da API e monitore limites (429 -> retry/backoff implementado).

## Próximos Passos (Sugestões)

- Adicionar API FastAPI para servir perguntas via HTTP.
- Implementar cache de embeddings para evitar recalcular o mesmo chunk.
- Adicionar testes unitários para chunking e busca.
- Suporte a múltiplos idiomas com detecção de linguagem.

---
Qualquer dúvida, abra uma issue ou adapte conforme necessário.
