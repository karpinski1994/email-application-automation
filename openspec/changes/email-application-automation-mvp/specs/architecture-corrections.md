# Email Application Automation MVP - Comprehensive Fix Spec

**CORRECTED ARCHITECTURE AS PER LATEST DESIGN DECISIONS**

## Architectural Pattern Correction

### Orchestrator: Deterministic Python Async Pipeline (NOT LLM Agent)

The main orchestrator is a **pure Python async pipeline**, NOT an LLM agent.

- Workflow is fixed: Scrape → Filter → Personalize → Email → Draft
- No dynamic branching - always the same steps
- Python controls the flow; Pydantic AI agents handle cognitive work inside tools

### Tools: Pydantic AI Agents for Cognitive Tasks

| Tool | Uses Pydantic AI Agent | Implementation |
|------|---------------------|----------------|
| **Filter** | ✓ Yes | `result_type=FilterDecision` with structured JSON |
| **CV Personalizer** | ✓ Yes | `result_type=CVData` -> HTML -> PDF |
| **Email Finder** | ✓ Yes | Multi-tool: API → parse description → guess |
| **Cover Letter** | ✓ Yes | System prompt enforcement |

---

## CORRECTIONS FROM FLAW ANALYSIS

### C1. Orchestrator Pattern - FIXED
**Original (WRONG):** "Pydantic AI agent orchestrator"  
**Corrected:** "Deterministic Python async orchestrator + Pydantic AI agentic tools"

### C2. Sequential vs Async - FIXED
**Original (WRONG):** "Sequential pipeline"  
**Corrected:** 
- For **local Ollama**: Semaphore(1) - sequential due to VRAM limits
- For **OpenAI**: Semaphore(5) - parallel works with cloud API
- Use `await asyncio.to_thread()` for blocking calls (WeasyPrint)

### C3. PDF Library - FIXED
**Original (WRONG):** reportlab  
**Corrected:** HTML + Jinja2 template + weasyprint

### C4. AnyMailFinder API - FIXED
**New (CORRECTED):** POST https://api.anymailfinder.com/v4/search/text.json

### C5. Apify API - FIXED
**Corrected:** POST /v2/acts/{actor_id}/run-sync-get-dataset-items

### C6. API Keys Config - FIXED
**New (CORRECTED):** All secrets in .env, NOT in config.yaml:
```yaml
# config.yaml - NO secrets here
search:
  urls: [...]
llm:
  provider: "local"
  model: "qwen2.5:7b"

# .env - secrets here
ANYMAILFINDER_API_KEY=xxx
APIFY_API_KEY=xxx
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx
```

### C7. Race Condition on processed_jobs.json - FIXED
**Original (WRONG):** JSON file read-modify-write  
**Corrected:** 
- Use asyncio.Lock() for file writes
- Or use SQLite (recommended for concurrent writes)
- Or use append-only JSON Lines format

### C8. Sync/Async Mismatch - FIXED
**Original (WRONG):** Sync OpenAI client  
**Corrected:** 
- Use AsyncOpenAI client
- Wrap blocking calls: `await asyncio.to_thread(weasyprint_func)`

### C9. drafts_created Calculation - FIXED
**Original (WRONG):** `len(qualifying) - len(errors)`  
**Corrected:** `len([r for r in results if r is None])`

### C10. PII Redaction - ADDED
Default privacy setting: `privacy.redact_pii: true`

### C11. Prompt Injection Sanitization - ADDED
Strip code blocks, limit context length

### C12. Local LLM Hardware Requirements - ADDED
| Model | VRAM Required | Recommended Hardware |
|-------|--------------|---------------------|
| qwen2.5:7b | ~8GB | M1/M2/M3 Mac, RTX 3060+ |
| llama3.2:3b | ~4GB | Most modern laptops |
| gemma2:9b | ~12GB | RTX 4090, M3 Pro Max |

### C13. Parallelism for Local vs Cloud LLM
**Local Ollama:** Semaphore(1) - sequential due to VRAM constraints  
**OpenAI:** Semaphore(5) - truly parallel

### C14. Context Window Management
**Original (WRONG):** Full CV + full job description  
**Corrected:** Truncate to prevent context overflow:
- job.description[:2000]
- cv_text[:3000]

### C15. Attribute Match Fix
**Original (WRONG):** `job.hiring_manager` vs `job.hiring_manager_name`  
**Corrected:** Use `job.hiring_manager_name` consistently

### C16. Dry-Run Mode
**Original (WRONG):** Only skips Gmail draft  
**Corrected:** Skips ALL external APIs:
- Apify: return mock data
- AnyMailFinder: return empty
- OpenAI/Ollama: return mock response
- Gmail: log only, no API call

---

## Hardware Requirements

### For Local LLM (Ollama)
| Model | RAM/VRAM | Typical Runtime |
|-------|----------|----------------|
| qwen2.5:7b | 8GB VRAM | ~30 tokens/sec |
| llama3.2:3b | 4GB VRAM | ~50 tokens/sec |
| gemma2:9b | 12GB VRAM | ~20 tokens/sec |

**WARNING:** Running Semaphore(5) with local Ollama will cause OOM or sequential execution.

### For Cloud LLM (OpenAI)
| Model | Cost/1k tokens | Context |
|-------|----------------|---------|
| gpt-4o-mini | $0.002 | 128k |
| gpt-4o | $0.01 | 128k |

---

## Parallelism Recommendation

```python
# FIXED: Use Semaphore based on LLM provider
if config.llm.provider == "local":
    semaphore = asyncio.Semaphore(1)  # Local: sequential
else:
    semaphore = asyncio.Semaphore(5)  # Cloud: parallel

# FIXED: Wrap blocking calls
async def generate_pdf(html: str, path: Path) -> None:
    await asyncio.to_thread(HTML(string=html).write_pdf, path)
```

---

## CLI Arguments - For __main__.py

```python
import argparse

parser = argparse.ArgumentParser(description="Email Application Automation")
parser.add_argument("--step", type=int, choices=[1,2,3,4,5,6,7], 
                   help="Start from step N (1=CV, 2=scrape, 3=filter, 4=personalize, 5=email, 6=letter, 7=draft)")
parser.add_argument("--skip-steps", type=str,
                   help="Comma-separated steps to skip (e.g., '2,3' skips scrape and filter)")
parser.add_argument("--rerun", action="store_true",
                   help="Force rerun: clear all intermediate data before running")
parser.add_argument("--dry-run", action="store_true",
                   help="Dry run: don't call any external APIs")
parser.add_argument("--count", type=int, default=50,
                   help="Limit number of jobs to process")
parser.add_argument("--provider", choices=["local", "openai"], default="local",
                   help="LLM provider: local (Ollama) or openai")
parser.add_argument("--verbose", action="store_true",
                   help="Verbose output")

args = parser.parse_args()
```

### Example Usage

```bash
# Full run from scratch
python -m app run

# Start from step 3 (filter), using existing CV and scraped jobs
python -m app run --step=3

# Skip scraping (use existing data)
python -m app run --skip-steps=2

# Force rerun everything
python -m app run --rerun

# Dry run (don't spend any credits)
python -m app run --dry-run

# Test with OpenAI
python -m app run --provider=openai

# Process only 10 jobs
python -m app run --count=10

# Combined: Start from step 5, only 5 jobs
python -m app run --step=5 --count=5
```
```