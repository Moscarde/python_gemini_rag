# Arquitetura de Roteamento: RAG vs Consultas de Métricas

Este documento descreve a arquitetura para rotear perguntas do usuário entre:
- Fluxo RAG existente (busca vetorial + Gemini para resposta)
- Novo fluxo de consultas em tabelas de métricas (valores agregados, filtros e períodos)

Sem mudanças de código nesta etapa — referência para futuras implementações.

---

## Objetivo

Decidir, para cada pergunta do usuário, se a resposta deve:
- Usar o RAG padrão (definições, explicações, conteúdo textual);
- Executar uma consulta segura e parametrizada em tabelas de métricas (contagens, somas, médias, por unidade, por período etc.).

Exemplos:
- "O que é subhue?" → RAG padrão
- "Quantos atendimentos tiveram na unidade Salgado Filho no dia de ontem" → Fluxo de métricas

---

## Visão geral

- Duas intenções alvo: `rag` e `metrics`.
- Um Router classifica a intenção e extrai slots (medida, unidade, período, filtros).
- Com base na intenção:
  - `rag`: segue o fluxo já implementado (similarity search + LLM para resposta);
  - `metrics`: monta e executa uma SQL a partir de templates allowlisted e retorna o valor formatado.

---

## Componentes

1) Router (classificação de intenção + extração de slots)
- Entrada: pergunta livre (texto).
- Saída: `{ intent: 'rag' | 'metrics', confidence: 0..1, slots: { medida, unidade, periodo, filtros } }`.
- Início por regras/regex + dicionários; evolução para classificador LLM com JSON estruturado e threshold.

2) Extrator de entidades/slots
- Entidades: medida (ex.: atendimentos), unidade (ex.: "Salgado Filho"), período ("ontem", datas), filtros adicionais.
- Normalização: mapear nomes → IDs; resolver datas relativas com timezone/config.

3) Planejador/Tradutor de consulta (Metrics Query Planner)
- Traduz slots válidos para SQL parametrizado via templates allowlisted.
- Ex.: `SELECT total FROM atendimentos_diarios WHERE unidade_id = $1 AND data = $2`.
- Sem SQL livre gerado por LLM.

4) Camada de dados de métricas
- Tabelas/materialized views com agregados: `atendimentos_diarios(unidade_id, data, total)`.
- Índices por `(unidade_id, data)`; partição por data conforme volume.

5) Compositor de resposta
- Formata o resultado numérico e adiciona contexto (unidade, período, fonte/atualização).

6) Fluxo RAG existente
- Inalterado; invocado apenas quando o Router indicar `rag`.

7) Fallbacks e desambiguação
- Confiança baixa → pedir esclarecimento (ex.: "Qual unidade?").
- Medida/filtro fora da allowlist → explicar limites e sugerir consultas suportadas.
- Timeout/erro SQL → mensagem de indisponibilidade; opcionalmente não cair para RAG.

---

## Contrato do Router (proposta)

Entrada:
- `text: str` (pergunta do usuário)
- `user_id?: str`
- `locale?: 'pt-BR'`

Saída:
- `intent: 'metrics' | 'rag'`
- `confidence: float`
- `slots: {`
  - `medida?: str` (ex.: 'atendimentos')
  - `unidade?: str | id`
  - `periodo?: { type: 'relative' | 'date' | 'range', value: any }`
  - `filtros?: dict`
  `}`

Erros/Degradação:
- Se incompleto/ambíguo, retornar `intent='rag'` com baixa confiança ou solicitar esclarecimento.

---

## Fluxo de execução

1) Normalização do texto (lowercase, locale, remoção de ruído básico).
2) Router classifica intenção e extrai slots.
3) Se `intent='metrics'` e `confidence >= threshold`:
   - Validar slots (unidade conhecida, período resolvido, medida suportada).
   - Construir SQL via template + parâmetros bindados.
   - Executar consulta e compor resposta.
4) Caso contrário → fluxo RAG padrão.
5) Logar intenção, confiança, latência e SQL template usado (sem dados sensíveis).

---

## Regras iniciais (MVP)

- Sugerir `metrics` quando encontrar:
  - Palavras-chave de medida: `quantos`, `quantidade`, `total`, `soma`, `média`, `taxa`.
  - Referências temporais: `hoje`, `ontem`, `no dia`, `última semana`, `entre X e Y`.
  - Filtros de unidade/local: `unidade`, nomes conhecidos (ex.: "Salgado Filho").
- Heurística: 1 medida + 1 tempo, ou 1 medida + 1 filtro de unidade → `metrics`; senão → `rag`.
- Lista de medidas e sinônimos em dicionário controlado.

---

## Extração e normalização de slots

- Medida: mapping de variações → chave canônica (ex.: "atendimentos", "nº de atendimentos" → `atendimentos`).
- Unidade: dicionário/ontologia de nomes → `unidade_id`; fuzzy match com cutoff e confirmação quando necessário.
- Período: resolver datas relativas (ex.: `ontem` → `YYYY-MM-DD` no timezone definido); ranges fechados.
- Limites: período máximo (ex.: 1 ano) para proteger performance.

---

## Planejamento/execução de consultas (seguras)

- Apenas templates allowlisted, por medida/período (ex.: diário, semanal, mensal).
- Parâmetros sempre bindados (sem interpolação de string).
- Exemplo de template (conceitual):
  - `SELECT total FROM atendimentos_diarios WHERE unidade_id = $1 AND data = $2;`
- Governança: versionar templates; revisar e auditar mudanças.

---

## Camada de dados de métricas

- Tabelas agregadas: `atendimentos_diarios(unidade_id INT, data DATE, total INT)`.
- Índices: `(unidade_id, data)`; considerar partições por `data`.
- ETL/atualização: definir janela e SLAs; armazenar `updated_at` para reporte de frescor.

---

## Composição da resposta

- Formato: "Ontem (YYYY-MM-DD), na unidade Salgado Filho, foram 123 atendimentos." 
- Adicionais: fonte, última atualização, notas de cobertura (ex.: range de dados disponível).

---

## Fallbacks e desambiguação

- Falta unidade: perguntar qual unidade ou usar padrão configurado (se fizer sentido).
- Períodos ambíguos: definir convenção (ex.: "última semana" = últimos 7 dias corridos) e documentar.
- Unidade não reconhecida: sugerir opções semelhantes (fuzzy match) para confirmação.
- Dados fora do range: informar o range disponível.

---

## Observabilidade e governança

- Telemetria: taxa de roteamento correto, precisão (amostragem revisada), latência por fluxo, falhas SQL.
- Feature flags: thresholds, ativação do classificador LLM.
- Auditoria: log de SQL template e parâmetros (seguros), versão do dicionário/ontologia.

---

## Segurança

- Allowlist de medidas, colunas e filtros; parâmetros sempre bindados.
- Limites de período e paginação; timeouts por consulta.
- Permissões por usuário/unidade (row-level security se aplicável).

---

## Integração sugerida no repositório

Pastas/arquivos propostos:
- `modules/router.py`: classificar intenção e extrair slots.
- `modules/metrics_intents.py`: dicionários, sinônimos, regras e validação.
- `modules/metrics_sql.py`: templates SQL e montagem parametrizada.
- `modules/metrics_answer.py`: formatação de respostas.
- `ask.py`: invocar o router e decidir entre `modules.rag` (existente) e o fluxo de métricas.
- `modules/config.py`: thresholds, timezone, mapeamentos de unidades e toggles.

Compatível com os módulos atuais (`modules/rag.py`, `modules/db.py`, etc.).

---

## Roadmap incremental

1) Fase 1 (MVP)
- Router por regras + templates SQL.
- Suporte à medida "atendimentos" e períodos relativos simples ("hoje", "ontem").
- Mapeamento fixo das unidades mais comuns.

2) Fase 2
- Classificador LLM com saída JSON estruturada (Pydantic) e threshold.
- Mais medidas/filtros e intervalos (ranges) com agregações.

3) Fase 3
- Materialized views, caching (chave: unidade+período+medida).
- Desambiguação ativa (perguntas clarificadoras) e métricas de qualidade.

---

## Próximos passos sugeridos (sem implementar)

- Definir a tabela alvo de métricas (ex.: `atendimentos_diarios`) e índices.
- Especificar dicionário de unidades (nome → id) e sinônimos de medidas.
- Escrever conjunto mínimo de templates SQL e testes de validação de parâmetros.
- Implementar o Router MVP por regras e logs de telemetria.
