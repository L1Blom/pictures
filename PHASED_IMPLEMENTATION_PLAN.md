# Phased Implementation Plan — Decoupled Analysis Pipeline

Based on [`PIPELINE_DECOUPLING_PROPOSAL.md`](PIPELINE_DECOUPLING_PROPOSAL.md).

Default mode stays `"single"` throughout every phase, so existing setups keep working unchanged until opted in.

---

## Phase 1 — Config Layer (purely additive)

**Goal:** Add `StepConfig` / `PipelineConfig` to the Settings stack. No behaviour changes.

### Files to change

| File | Change |
|------|--------|
| `src/picture_analyzer/config/defaults.py` | Add `DEFAULT_PIPELINE_MODE = "single"` and per-step defaults |
| `src/picture_analyzer/config/settings.py` | Add `StepConfig`, `PipelineConfig`; add `pipeline` field to `Settings` |
| `src/picture_analyzer/config/__init__.py` | Export new models |
| `config.yaml.example` | Add commented `pipeline:` block with every knob documented |

### Tasks

1. Add to `defaults.py`:
   ```python
   DEFAULT_PIPELINE_MODE = "single"   # "single" | "stepped"
   DEFAULT_STEP_ENABLED = True
   ```

2. Add to `settings.py` (after `PromptConfig`):
   ```python
   class StepConfig(BaseModel):
       enabled: bool = True
       provider: Optional[str] = None
       model: Optional[str] = None
       max_tokens: Optional[int] = None
       prompt_template: Optional[str] = None

   class PipelineConfig(BaseModel):
       mode: str = Field(default="single", pattern="^(single|stepped)$")
       metadata: StepConfig = Field(default_factory=StepConfig)
       location: StepConfig = Field(default_factory=StepConfig)
       enhancement: StepConfig = Field(default_factory=StepConfig)
       slide_profiles: StepConfig = Field(default_factory=StepConfig)
   ```

3. Add `pipeline: PipelineConfig = Field(default_factory=PipelineConfig)` to `Settings`.

4. Add `resolve_step_config()` helper in `src/picture_analyzer/config/settings.py`
   (or a new `src/picture_analyzer/config/resolver.py`):
   ```python
   def resolve_step_config(step: StepConfig, settings: Settings) -> dict:
       provider = step.provider or settings.analyzer_provider
       base = settings.openai if provider == "openai" else settings.ollama
       return {
           "provider": provider,
           "model": step.model or base.model,
           "max_tokens": step.max_tokens or getattr(base, "max_tokens", None),
           "prompt_template": step.prompt_template,
       }
   ```

### Tests to write (`tests/unit/test_config.py` additions)

- Default `PipelineConfig()` has `mode="single"` and all steps enabled.
- `PA_PIPELINE__MODE=stepped` env var is picked up correctly.
- `PA_PIPELINE__LOCATION__MODEL=gpt-4o` overrides only the location step.
- `PA_PIPELINE__SLIDE_PROFILES__ENABLED=false` disables slide step.
- `resolve_step_config` falls back to global provider when step has no override.
- `resolve_step_config` uses step-level values when set.

### Acceptance criteria

- All existing tests still pass.
- `Settings()` loads without error; `settings.pipeline.mode == "single"`.
- YAML `pipeline: {mode: stepped}` round-trips through `config/loader.py`.

---

## Phase 2 — Prompt Decomposition

**Goal:** Split the monolithic `ANALYSIS_PROMPT` into four focused template files and a loader. Analyzers still work (single-call fallback assembles the same combined prompt).

### Files to create / change

| File | Change |
|------|--------|
| `src/picture_analyzer/data/templates/metadata.txt` | Sections 1–11 (scene, objects, people, mood, time, weather, era, …) |
| `src/picture_analyzer/data/templates/location.txt` | Section 12 (geographic reasoning from visual clues) |
| `src/picture_analyzer/data/templates/enhancement.txt` | Sections 13–18 (lighting, color, sharpness recommendations) — English only |
| `src/picture_analyzer/data/templates/slide_profiles.txt` | Section 19 (profile classification + confidence) — English only |
| `src/picture_analyzer/data/__init__.py` | Add `PromptLoader` class (or put it in `data/loader.py`) |
| `src/picture_analyzer/analyzers/openai.py` | Use `PromptLoader` instead of bare `ANALYSIS_PROMPT` import |
| `src/picture_analyzer/analyzers/ollama.py` | Same |

### Tasks

1. **Extract** each section from the current `ANALYSIS_PROMPT` in `prompts.py` into its own `.txt` file. Keep placeholder tokens: `{language}`, `{context_hint}`.

2. **Implement `PromptLoader`:**
   ```python
   class PromptLoader:
       def load(self, name: str, **kwargs) -> str:
           """Load a named template and substitute kwargs."""

       def combined(self, sections: list[str], **kwargs) -> str:
           """Concatenate multiple sections — used by the single-call path."""
   ```

3. **Update `OpenAIAnalyzer` and `OllamaAnalyzer`**: replace the `ANALYSIS_PROMPT` import with `PromptLoader().combined([...])`. Behaviour must be identical to before.

4. Keep `prompts.py` at the repo root as a thin backward-compat shim that re-exports `ANALYSIS_PROMPT` via `PromptLoader().combined(...)`.

### Tests to write

- Each template file loads without error.
- `{language}` substitution works in `metadata.txt`.
- `combined()` produces the same text as the original `ANALYSIS_PROMPT` (snapshot test).
- Missing template name raises a clear `FileNotFoundError`.

### Acceptance criteria

- Analyzer output unchanged (same JSON structure from same image).
- Templates live in `data/templates/`; no hardcoded strings remain in `openai.py` / `ollama.py`.

---

## Phase 3 — Pipeline Module

**Goal:** Implement the `AnalysisStep` protocol and all five concrete steps, then wire them into `AnalysisPipeline`. The pipeline is not yet connected to the CLI.

### New module layout

```
src/picture_analyzer/pipeline/
    __init__.py          ← exports AnalysisPipeline
    protocols.py         ← AnalysisStep Protocol
    steps.py             ← MetadataStep, LocationStep, EnhancementStep, SlideProfileStep
    geo_step.py          ← GeocodingStep (wraps NominatimGeocoder)
    pipeline.py          ← AnalysisPipeline orchestrator
```

### Tasks

1. **`protocols.py`** — define the protocol:
   ```python
   class AnalysisStep(Protocol):
       name: str
       def run(
           self,
           image: ImageData,
           context: AnalysisContext,
           partial: AnalysisResult,
       ) -> AnalysisResult: ...
   ```

2. **`steps.py`** — one class per LLM step:
   - Constructor receives a resolved config dict (from `resolve_step_config`).
   - Instantiates the right `OpenAIAnalyzer` or `OllamaAnalyzer` based on `provider`.
   - Calls the analyzer with a **section-specific prompt** via `PromptLoader`.
   - Merges the partial result using `partial.model_copy(update={...})`.
   - Skips (returns `partial` unchanged) when `context.<flag>` is `False` or step is disabled.

3. **`geo_step.py`** — `GeocodingStep`:
   - Reads `partial.location` for a place name string.
   - Calls `NominatimGeocoder` (already in `geo/nominatim.py`).
   - Writes coordinates back via `partial.model_copy(update={"location": ...})`.
   - Skips when `context.detect_location` is `False` or `partial.location` is `None`.

4. **`pipeline.py`** — `AnalysisPipeline`:
   ```python
   class AnalysisPipeline:
       def __init__(self, steps: list[AnalysisStep]): ...
       def run(self, image: ImageData, context: AnalysisContext) -> AnalysisResult:
           partial = AnalysisResult.empty()
           for step in self.steps:
               partial = step.run(image, context, partial)
           return partial
   ```

5. **Factory function** `build_pipeline(settings: Settings) -> AnalysisPipeline`:
   - Reads `settings.pipeline` to determine which steps to include and their configs.
   - Returns a ready-to-use pipeline.

### Tests to write (`tests/unit/test_pipeline_*.py`)

- Each step skips correctly when corresponding context flag is `False`.
- Each step calls the correct provider based on `StepConfig`.
- `GeocodingStep` skips when `partial.location` is `None`.
- `AnalysisPipeline.run()` accumulates partial results across steps.
- `build_pipeline` returns steps in the canonical order.
- Integration: `mode=stepped` + mock analyzers produces a valid `AnalysisResult`.

### Acceptance criteria

- `AnalysisPipeline` with all steps enabled on a test image produces an `AnalysisResult` structurally equivalent to the single-call result.
- Disabling a step (e.g. `slide_profiles.enabled=False`) skips that API call.
- `GeocodingStep` with a real place name resolves coordinates.

---

## Phase 4 — CLI Integration

**Goal:** Wire `pipeline.mode` into the CLI so users can opt into the stepped pipeline.

### Files to change

| File | Change |
|------|--------|
| `src/picture_analyzer/cli/app.py` | Route `analyze` command through `AnalysisPipeline` when `mode=stepped` |
| `src/picture_analyzer/cli/commands/__init__.py` | Export updated analyze command |
| `config.yaml.example` | Un-comment `pipeline: {mode: stepped}` example |

### Tasks

1. In the analyze execution path, after loading `settings`:
   ```python
   if settings.pipeline.mode == "stepped":
       pipeline = build_pipeline(settings)
       result = pipeline.run(image_data, context)
   else:
       result = analyzer.analyze(image_data, context)   # existing path
   ```

2. Add optional `--pipeline-mode [single|stepped]` CLI flag that overrides `settings.pipeline.mode` for the current invocation.

3. Ensure the existing `--no-location`, `--no-enhancements`, `--no-slide-profiles` flags still work in both modes (they set `AnalysisContext` flags that each step already respects).

### Tests to write (`tests/unit/test_cli.py` + integration)

- `--pipeline-mode single` keeps using the legacy path.
- `--pipeline-mode stepped` instantiates `AnalysisPipeline`.
- Conflicting flags (`--no-location` + stepped mode) correctly skip the location step.
- `PA_PIPELINE__MODE=stepped` env var activates stepped mode.

### Acceptance criteria

- `picture-analyzer analyze photo.jpg` (no flags) behaves identically to before.
- `picture-analyzer analyze photo.jpg --pipeline-mode stepped` runs the new pipeline.
- Both produce the same JSON output schema.

---

## Phase 5 — Hardening & Cleanup

**Goal:** Full test pass, documentation, and any rough edges smoothed out.

### Tasks

1. **Parity test**: run both modes on the same image set, diff the JSON output, assert structural equivalence.
2. **Backward-compat check**: verify `PA_PIPELINE__MODE` unset → `mode=single` → no new code paths exercised.
3. **Error handling**: each step should catch API errors and either raise a typed exception or return a partial result with a logged warning (decide policy here).
4. **Update `README.md`**: add a `Pipeline Modes` section linking to `PIPELINE_DECOUPLING_PROPOSAL.md`.
5. **Deprecate** the `prompts.py` shim at repo root — add a `DeprecationWarning` import warning pointing to `PromptLoader`.
6. **Performance baseline**: log time-per-step so users can see the tradeoff between monolithic and stepped mode.

### Acceptance criteria

- Full `pytest` run is green.
- No regressions on existing integration tests in `tests/integration/`.
- `picture-analyzer --help` shows `--pipeline-mode` option.

---

## Dependency Graph

```
Phase 1 (Config)
    └── Phase 2 (Prompt Decomp)
            └── Phase 3 (Pipeline Module)
                    └── Phase 4 (CLI Integration)
                                └── Phase 5 (Hardening)
```

Phases are strictly sequential. Each phase ends with a green test suite before the next begins.

---

## Risk Notes

| Risk | Mitigation |
|------|-----------|
| Token count differs per step vs. combined | Each step template is sized accordingly; validate with real image |
| JSON parsing breaks when only partial sections are returned | Each step's `PromptLoader` template enforces its own JSON schema subset |
| `NominatimGeocoder` rate-limit in CI | Already cached — keep existing cache fixture in `conftest.py` |
| `AnalysisResult` frozen model copy overhead | `.model_copy(update=...)` is O(fields); acceptable for 4–5 steps |
