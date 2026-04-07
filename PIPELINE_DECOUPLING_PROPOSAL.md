# Decoupled Analysis Pipeline: Step-Specific Models

## The Core Problem

Currently everything fires in **one monolithic prompt** to one model. This is suboptimal because:
- Location detection needs a model with strong geographic/OCR/sign-reading ability
- Image metadata needs visual scene understanding
- Enhancement recommendations need photographic/technical reasoning
- Slide profile detection is a classification task

## Proposed Architecture: `AnalysisPipeline` with `Step` abstraction

```
Input Image
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  AnalysisPipeline(steps=[...], context=ctx)          │
│                                                      │
│  Step 1: MetadataStep          ← model A (e.g. llava / gpt-4o-mini)
│           prompt: sections 1–11 (scene, mood, etc.)  │
│           output: AnalysisResult.metadata            │
│                                                      │
│  Step 2: LocationStep          ← model B (e.g. gpt-4o / best vision)
│           prompt: section 12 only                    │
│           output: AnalysisResult.location            │
│                                                      │
│  Step 3: EnhancementStep       ← model C (e.g. gpt-4o-mini, cheap)
│           prompt: sections 13–18                     │
│           output: AnalysisResult.enhancement         │
│                                                      │
│  Step 4: SlideProfileStep      ← model D or classifier
│           prompt: section 19 only                    │
│           output: AnalysisResult.slide_profiles      │
│                                                      │
│  Step 5: GeocodingStep         ← NominatimGeocoder (no LLM)
│           input:  location from Step 2               │
│           output: coordinates + enriched location    │
│                                                      │
│  Steps compose: each receives prior accumulated result│
└──────────────────────────────────────────────────────┘
    │
    ▼
  merged AnalysisResult  →  metadata writer → JSON save
```

## Key Design Decisions

### 1. Each step is a protocol

```python
class AnalysisStep(Protocol):
    name: str
    def run(self, image: ImageData, context: AnalysisContext,
            partial: AnalysisResult) -> AnalysisResult: ...
```

Each step receives the accumulated result so a later step (e.g. enhancement) can read what the metadata step found about scene type.

### 2. Each step has its own model config

A new `StepConfig` Pydantic model captures the per-step overrides. All fields are optional — omitting one means the step inherits from the matching global provider config (`openai`, `ollama`).

```python
# src/picture_analyzer/config/settings.py  (additions)

class StepConfig(BaseModel):
    """Per-step model/provider overrides. Unset fields fall back to global provider config."""
    enabled: bool = True
    provider: Optional[str] = None          # "openai" | "ollama" — falls back to analyzer_provider
    model: Optional[str] = None             # falls back to openai.model / ollama.model
    max_tokens: Optional[int] = None        # falls back to openai.max_tokens
    prompt_template: Optional[str] = None  # falls back to built-in template


class PipelineConfig(BaseModel):
    """Pipeline execution and per-step configuration."""
    mode: str = Field(default="single", pattern="^(single|stepped)$")  # single = legacy monolithic call
    metadata: StepConfig = Field(default_factory=StepConfig)
    location: StepConfig = Field(default_factory=StepConfig)
    enhancement: StepConfig = Field(default_factory=StepConfig)
    slide_profiles: StepConfig = Field(default_factory=StepConfig)
    # geocoding has no model — it delegates to GeoConfig
```

`PipelineConfig` is added as a new top-level field on the existing `Settings` class alongside `openai`, `ollama`, `geo`, etc. The step config is **resolved at runtime** by a small helper that merges step-level overrides onto global provider defaults:

```python
def resolve_step_config(step: StepConfig, settings: Settings) -> dict:
    """Return the effective provider/model/max_tokens for a step."""
    provider = step.provider or settings.analyzer_provider
    base = settings.openai if provider == "openai" else settings.ollama
    return {
        "provider": provider,
        "model": step.model or base.model,
        "max_tokens": step.max_tokens or getattr(base, "max_tokens", None),
        "prompt_template": step.prompt_template,
    }
```

The corresponding `config.yaml` section:

```yaml
# config.yaml
analyzer_provider: "ollama"   # global default, used when a step has no provider override

openai:
  model: "gpt-4o-mini"
  max_tokens: 4096

ollama:
  model: "llava:7b"
  host: "http://127.0.0.1:11434"

pipeline:
  mode: stepped               # "single" keeps the legacy monolithic path
  metadata:
    provider: ollama          # use local llava for cheap scene description
    model: llava:7b
  location:
    provider: openai
    model: gpt-4o             # best geographic reasoning
    max_tokens: 1024          # location response is small
  enhancement:
    provider: openai
    model: gpt-4o-mini        # cheaper, sufficient for filter recommendations
  slide_profiles:
    enabled: false            # skip entirely when not processing slides
```

Env var overrides follow the existing `PA_` prefix + double-underscore nesting convention from `pydantic-settings`:

```bash
# override location step to use a different model
PA_PIPELINE__LOCATION__MODEL=gpt-4o
PA_PIPELINE__LOCATION__PROVIDER=openai

# disable slide profile detection
PA_PIPELINE__SLIDE_PROFILES__ENABLED=false

# switch entire pipeline to single-call mode (legacy)
PA_PIPELINE__MODE=single
```

### 3. Prompt templates become separate files

The monolithic `ANALYSIS_PROMPT` in `prompts.py` splits into separate files under `src/picture_analyzer/data/templates/`:

| File | Content | Language |
|------|---------|----------|
| `metadata.txt` | Sections 1–11: objects, persons, weather, mood, time, scene, etc. | `{language}` |
| `location.txt` | Section 12: geographic reasoning from visual clues | `{language}` |
| `enhancement.txt` | Sections 13–18: lighting, color, sharpness, contrast, recommendations | Always English |
| `slide_profiles.txt` | Section 19: profile classification with confidence scores | Always English |

Each is loaded by a `PromptLoader` that handles `{language}` and `{context_hint}` substitutions. A stub for this already exists in `src/picture_analyzer/data/templates/`.

### 4. Geocoding as a non-LLM step in the same pipeline

The `GeocodingStep` doesn't call an AI; it calls `NominatimGeocoder`. It fits naturally as a pipeline step because it reads from `partial.location` and writes `partial.location.coordinates`. `NominatimGeocoder` already exists in `src/picture_analyzer/geo/` — it just needs wrapping in the step interface.

### 5. Selective execution

The existing `AnalysisContext` fields (`detect_location`, `recommend_enhancements`, `detect_slide_profiles`) map 1:1 to step enable flags. A step can be skipped cheaply:

```python
if not context.detect_location:
    return partial  # pass-through, no API call
```

## What This Enables

| Goal | How |
|------|-----|
| Best geo model for location | `location.model: gpt-4o` while keeping `metadata.model: llava` |
| Skip geo entirely on batch | `PA_PIPELINE__STEPS__LOCATION__ENABLED=false` |
| Run enhancement with a specialist model | Swap only `enhancement.provider` |
| Offline/local-only pipeline | All steps → `provider: ollama` |
| Cost optimization | Cheap model for metadata, expensive only for location |
| Slide-only batch | Disable all steps except `slide_profiles` + `geocoding` |

## Relationship to Existing Code

This doesn't require a full rewrite — the refactored `src/` layer already has most of the pieces:

| Existing | Role in new design |
|----------|--------------------|
| `OpenAIAnalyzer` / `OllamaAnalyzer` | Become **step executors** — each step instantiates the analyzer it needs |
| `core/interfaces.py` → `Analyzer` protocol | The per-step analyzer call surface — already correct |
| `AnalysisContext` flags | Become **step enable/disable** flags |
| `AnalysisResult` (Pydantic, immutable) | Accumulated across steps via `.model_copy(update=...)` |
| `NominatimGeocoder` | Wrapped as `GeocodingStep` |
| `data/templates/` | Destination for split prompt templates |
| `config/settings.py` → `PromptConfig` | `prompt_template` field moves into `StepConfig` |
| `config/defaults.py` | Add `DEFAULT_PIPELINE_MODE = "single"` and per-step defaults |

The **legacy** `picture_analyzer_legacy.py` / `_get_legacy_modules()` path stays unchanged. Setting `PA_PIPELINE__MODE=single` (or omitting `pipeline` from `config.yaml` entirely) routes straight to it, so existing setups are unaffected.

## Suggested Implementation Order

1. **Add `StepConfig` + `PipelineConfig`** to `settings.py` and `DEFAULT_PIPELINE_MODE` to `defaults.py` — purely additive, nothing breaks
2. **Add `pipeline:` block to `config.yaml.example`** documenting all knobs with comments
3. **Split `prompts.py`** into 4 template files under `data/templates/` — no logic change yet
4. **Implement `AnalysisStep` protocol** + 4 concrete steps in a new `src/picture_analyzer/pipeline/` module, each calling `resolve_step_config()` to get its effective provider/model
5. **Wrap `NominatimGeocoder`** as `GeocodingStep` (reads from `GeoConfig`, not `StepConfig`)
6. **Add `AnalysisPipeline`** that sequences steps and merges partial `AnalysisResult` via `.model_copy(update=...)`
7. **Wire `PA_PIPELINE__MODE`** in the CLI — `single` routes to the existing monolithic path, `stepped` routes to `AnalysisPipeline`
