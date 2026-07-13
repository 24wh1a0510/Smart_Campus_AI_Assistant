# 🎓 College FAQ Chatbot — RAG + Evaluation Suite

A production-style Retrieval-Augmented Generation chatbot that answers college FAQs
strictly from a DOCX knowledge base, with citations, refusal handling, prompt-injection
defense, and a full automated evaluation suite (functional / quality / safety / security /
robustness / performance / context / RAGAS).

See [`spec.md`](./spec.md) for the full product & engineering specification.

## Stack
- **UI:** Streamlit (custom CSS, glassmorphism, premium SaaS styling)
- **Orchestration:** LangChain (`RecursiveCharacterTextSplitter`)
- **Vector DB:** ChromaDB (persistent, cosine similarity)
- **Generation / Judge / Test-gen LLM:** GPT-4o Mini via **OpenRouter**
- **Embeddings:** `text-embedding-3-small` via **OpenAI direct** (OpenRouter doesn't proxy embeddings)
- **Evaluation:** RAGAS (faithfulness, answer relevancy, context precision/recall) + custom LLM judge

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # or your preferred env manager
pip install -r requirements.txt

cp .env.example .env
# then fill in OPENROUTER_API_KEY and OPENAI_API_KEY in .env
```

A sample knowledge base is already at `data/college_kb.docx`. Replace it with your own
DOCX (same path, or update `KB_DOCX_PATH` in `.env`) — the app re-indexes automatically
when the file content or chunk settings change (content hash comparison), so you don't
pay re-indexing cost on every restart.

## Run

```bash
streamlit run app.py
```

Open the app, and:
1. The sidebar shows live KB status, chunk count, model info, and retrieval settings.
2. Use the chat page to ask questions — every answer includes citation cards, an
   expandable "retrieved context" panel, a confidence score, and latency badges.
3. Switch to **📊 Evaluation Dashboard** and click **Run Full Evaluation** to:
   - auto-generate test questions per KB section (+ a fixed bank of adversarial/security probes)
   - score every case across 6 LLM-judged dimensions (functional, quality, safety,
     security, robustness, context) plus RAGAS metrics
   - view pass rate, dimension breakdown, latency chart, failures table, and
     auto-generated recommendations

Evaluation output is also persisted to `evaluation/results/latest_report.json`.

## Project layout

```
app.py                     # Streamlit entrypoint
app/config/settings.py     # typed, env-driven config
app/rag/                   # loader, chunker, embeddings, vectorstore, llm_client, generator, indexer
app/prompts/templates.py   # system prompt, grounding template, refusal template
app/utils/                 # security (injection heuristics), timing/logging
app/evaluation/            # test_generator, judge, ragas_eval, report
app/components/            # sidebar, chat, dashboard UI components
app/styles/theme.py        # custom CSS
data/college_kb.docx       # sample knowledge base (replace with your own)
vector_db/                 # ChromaDB persistence (gitignored)
evaluation/results/        # latest_report.json output (gitignored)
```

## Design notes
- **Refusal policy:** if the top retrieval similarity is below `MIN_RELEVANCE` (default
  0.25) or the model itself determines the context is insufficient, the bot returns a
  fixed refusal message instead of generating freely.
- **Prompt injection defense:** the system prompt explicitly instructs the model to
  treat any embedded instructions in context/user input as content, not commands. A
  lightweight heuristic (`app/utils/security.py`) also flags suspicious phrasing in the
  UI so you can see when a message looked like an injection attempt, independent of
  whether the model actually complied.
- **Citations:** retrieved chunks are numbered `[1]`, `[2]`, ... and the model is
  instructed to cite them inline; the UI renders those as citation cards under each answer.

## Known limitations / stretch goals
Dark mode, PDF ingestion, multi-document KBs, OCR, auth, analytics, true token
streaming, and hybrid (BM25 + vector) retrieval are documented as stretch goals in
`spec.md` but not implemented in this pass.

---

## 📡 Observability & Governance

Production-ready observability and governance is built-in and enabled by default.
All modules are fully modular — the chatbot works fine even if you disable them.

### What's included

| Module | Location | What it does |
|---|---|---|
| LLM Logger | `app/observability/llm_logger.py` | Logs every LLM call (tokens, latency, cost, status) to `evaluation/results/llm_calls.jsonl` |
| Metrics | `app/observability/metrics.py` | Aggregates rolling stats (avg/p95 latency, total cost, error rate, per-type breakdown) |
| Alerts | `app/observability/alerts.py` | Threshold engine — fires warnings/criticals for latency, cost, error rate |
| A/B Testing | `app/observability/ab_testing.py` | Hash-based session variant picker (control / concise / empathetic prompt variants) |
| Governance Prompt | `app/governance/system_prompt.py` | 15-rule governance-aware system prompt (transparency, privacy, safety, fairness, security, human oversight) |
| Input Validator | `app/governance/input_validator.py` | PII detection, prompt injection, harmful content, length checks — returns `ValidationResult` |
| Governance Report | `app/governance/report_generator.py` | Generates a structured compliance report from log + eval data |
| Giskard Scanner | `app/scanning/giskard_scanner.py` | Vulnerability scan wrapper (optional — `pip install giskard`) |
| DeepEval Runner | `app/scanning/deepeval_runner.py` | Hallucination/relevancy eval (optional — `pip install deepeval`) |
| Promptfoo Runner | `app/scanning/promptfoo_runner.py` | Red-teaming config + CLI runner (optional — `npm install -g promptfoo`) |
| Dashboard | `app/components/observability_dashboard.py` | Streamlit page: metrics, alerts, A/B table, governance report, scan controls |

### Enable / disable via `.env`

```env
# Governance (both default to true)
ENABLE_GOVERNANCE_PROMPT=true
ENABLE_INPUT_VALIDATION=true

# Observability logging (default true)
ENABLE_OBSERVABILITY_LOGGING=true

# Cost per 1 000 tokens (gpt-4o-mini defaults)
COST_PER_1K_INPUT_TOKENS=0.00015
COST_PER_1K_OUTPUT_TOKENS=0.00060

# Alert thresholds
ALERT_LATENCY_WARN_MS=3000
ALERT_LATENCY_CRITICAL_MS=6000
ALERT_ERROR_RATE_WARN=0.05
ALERT_COST_WARN_USD=0.10
```

### Using the Observability dashboard

1. Run the app: `streamlit run app.py`
2. Click **📡 Observability** in the sidebar navigation
3. **Live Metrics & Alerts tab** — see token usage, cost, latency trend, A/B results, recent call log
4. **Governance Report tab** — click "Generate Report" for a compliance summary
5. **Vulnerability Scanning tab** — run Giskard / DeepEval / Promptfoo on demand

### Installing optional scanning tools

```bash
# Giskard
pip install giskard

# DeepEval
pip install deepeval

# Promptfoo (requires Node.js)
npm install -g promptfoo
```

### Updated project layout

```
app/
  observability/
    llm_logger.py       # JSONL call logger
    metrics.py          # rolling stats aggregator
    alerts.py           # threshold alert engine
    ab_testing.py       # A/B prompt variant selector
    __init__.py
  governance/
    system_prompt.py    # 15-rule governance-aware system prompt
    input_validator.py  # PII, injection, harmful content detection
    report_generator.py # compliance report builder
    __init__.py
  scanning/
    giskard_scanner.py  # Giskard wrapper (optional)
    deepeval_runner.py  # DeepEval wrapper (optional)
    promptfoo_runner.py # Promptfoo config + CLI runner (optional)
    __init__.py
  components/
    observability_dashboard.py  # new Streamlit page (no existing pages changed)
evaluation/results/
  llm_calls.jsonl           # LLM call log (observability)
  governance_report.json    # latest governance report
  giskard_report.json       # Giskard scan output (if run)
  deepeval_report.json      # DeepEval output (if run)
  promptfoo_config.yaml     # generated red-teaming config
```
