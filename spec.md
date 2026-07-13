# College FAQ Chatbot – Product Specification
## 1. Overview
A production-grade RAG-powered chatbot that answers college-related questions using a custom knowledge base while providing grounded citations, conversation memory, automated evaluation, and RAGAS scoring.
---
# 2. Goals
- Accurate answers from uploaded documents
- Zero hallucination policy
- Source citations for every response
- Professional modern UI
- Persistent vector database
- Complete evaluation suite
- Easy deployment
---
# 3. User Personas
### Student
- Admission questions
- Fees
- Placements
- Departments
### Parent
- Scholarships
- Hostel
- Contact information
### Faculty
- Research
- Departments
- Facilities
---
# 4. Functional Requirements
## Knowledge Base
- Upload DOCX
- Parse document
- Preserve metadata
- Display indexing status
## Indexing
- Recursive chunking
- Metadata
- Chroma persistence
- Reload without re-indexing
## Retrieval
- Semantic search
- Top-K retrieval
- Section filtering
- Metadata-aware search
## Chat
- Multi-turn memory
- Streaming responses
- Suggested questions
- Citations
- Refusal handling
## Evaluation
- Automatic test generation
- Judge pipeline
- Eight evaluation dimensions
- RAGAS metrics
- Downloadable reports
---
# 5. Non Functional Requirements
- Fast retrieval
- Modular architecture
- Maintainability
- Security
- Extensibility
---
# 6. Tech Stack
Frontend
- Streamlit
Backend
- Python
LLM
- GPT-4o Mini
Embeddings
- text-embedding-3-small
Framework
- LangChain
Database
- ChromaDB
Evaluation
- RAGAS
---
# 7. Folder Structure
app/
components/
rag/
evaluation/
prompts/
utils/
styles/
config/
data/
vector_db/
assets/
---
# 8. UI Layout
Sidebar
- Logo
- KB Status
- Metrics
- Retrieval Settings
- Filters
Main
- Chat
- Sources
- Confidence
- Metrics
Evaluation
- Dashboard
- Charts
- Tables
- Reports
---
# 9. UI Theme
Style
- Glassmorphism
- Soft shadows
- Rounded corners
- Premium spacing
- Rich gradients
---
# 10. RAG Pipeline
Load
↓
Split
↓
Embed
↓
Store
↓
Retrieve
↓
Prompt
↓
Generate
↓
Cite
---
# 11. Metadata
Every chunk stores
- filename
- section
- page
- chunk_id
---
# 12. Prompt Strategy
System Prompt
- Context only
- Never hallucinate
- Always cite
- Refuse unsupported answers
- Handle conflicting sources
---
# 13. Evaluation
Functional
Quality
Safety
Security
Robustness
Performance
Context
RAGAS
---
# 14. Dashboard
Summary
Pass Rate
Dimension Cards
Latency
RAGAS Charts
Failure Analysis
Recommendations
---
# 15. Performance Targets
Index
<15 s
Retrieval
<300 ms
Generation
<5 s
---
# 16. Security
Prompt injection defense
Role enforcement
Input validation
No system prompt leakage
---
# 17. Deployment
Docker
requirements.txt
.env
GitHub-ready
README
---
# 18. Stretch Goals
- Dark mode
- PDF support
- Multi-document search
- OCR
- Authentication
- Analytics
- Streaming tokens
- Hybrid retrieval

---
# 19. Implementation Notes (Engineering Addendum)

**Model routing:** GPT-4o Mini is called via OpenRouter (`openai/gpt-4o-mini`) for generation, the judge, and the test generator. `text-embedding-3-small` is called directly against OpenAI's embeddings endpoint (OpenRouter does not proxy embeddings), using a separate `OPENAI_API_KEY`. Both keys are read from `.env`.

**Chunking:** `RecursiveCharacterTextSplitter`, chunk_size=800, overlap=120, configurable from the sidebar (re-indexes on change).

**Vector store:** ChromaDB `PersistentClient`, collection `college_kb`, cosine distance. Index is only rebuilt if the source DOCX hash changes or the user forces a reindex.

**Citations:** each retrieved chunk carries `{source, section, chunk_id}`; the generator is instructed to tag claims with `[n]` markers mapped to a citation list rendered as cards under the answer.

**Refusal:** if max similarity score across retrieved chunks is below `MIN_RELEVANCE` (default 0.25) or the LLM itself determines the context doesn't support an answer, the bot returns a fixed refusal template instead of generating freely.

**Eval suite:** `evaluation/test_generator.py` produces N synthetic Q/A pairs per section via LLM; `evaluation/judge.py` scores functional/quality/safety/security/robustness/performance/context dimensions (1-5 scale) via LLM-as-judge; `evaluation/ragas_eval.py` computes faithfulness, answer relevancy, context precision, context recall via RAGAS; results are merged into `evaluation/results/latest_report.json` and rendered on the dashboard page.
