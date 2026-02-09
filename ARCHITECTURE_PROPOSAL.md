# Architecture Redesign Proposal

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Proposed Architecture](#2-proposed-architecture)
3. [Package Structure](#3-package-structure)
4. [Design Decisions & Alternatives](#4-design-decisions--alternatives)
5. [Tradeoff Matrix](#5-tradeoff-matrix)
6. [Configuration System](#6-configuration-system)
7. [Plugin / Provider Architecture](#7-plugin--provider-architecture)
8. [Data Flow & Pipeline](#8-data-flow--pipeline)
9. [Hardcoded Values Inventory](#9-hardcoded-values-inventory)
10. [Migration Path](#10-migration-path)

---

## 1. Current State Analysis

### 1.1 What Works Well
- Clear separation of concerns at the file level (analyzer, enhancer, metadata, geo)
- Description.txt context enriches AI analysis meaningfully
- Geocoding cache prevents redundant API calls
- Metadata embedding (EXIF/XMP) is thorough
- CLI covers both single-image and batch workflows

### 1.2 Structural Problems

| Problem | Where | Impact |
|---------|-------|--------|
| **Flat file layout** — 17 `.py` files in root, no packages | Everywhere | Cannot `pip install`, no namespace isolation, import collisions risk |
| **No formal packaging** — no `pyproject.toml`, `setup.py` | Root | Not installable, no version, no entry points |
| **Hardcoded AI model** | `config.py`, `picture_analyzer.py` | Locked to `gpt-4o-mini`, can't switch providers |
| **Hardcoded prompt** | `prompts.py` | Single monolithic string, not composable or overridable |
| **Hardcoded slide profiles** | `slide_restoration.py` | Can't add profiles without editing source |
| **Hardcoded output naming** | `cli_commands.py` | `_analyzed.jpg`, `_enhanced.jpg` — not configurable |
| **Hardcoded languages** | `exif_handler.py` | Only `en`/`nl` translations, adding one = editing source |
| **Hardcoded port & template** | `description_editor_app.py` | Port 7000, Dutch-only template |
| **JPEG quality repeated** | 6+ files | `95` scattered everywhere, inconsistent |
| **Pure-Python pixel ops** | `enhancement_filters.py` | Extremely slow on large images |
| **No tests** | Everywhere | Zero automated tests |
| **No error recovery** | `cli_commands.py` | Batch processing fails silently or aborts |
| **Tight coupling** | `picture_analyzer.py` | Directly instantiates `MetadataManager`, `openai.OpenAI` |
| **`metadata_config.py` unused** | `exif_handler.py` | Imported but the mapping is never applied |
| **`description_editor_app` globs only `.jpg`** | `description_editor_app.py` | Misses all other supported formats |
| **Report generator bug** | `report_generator.py` ~L286 | References undefined `analysis` variable |

### 1.3 Dependency Graph (Current)

```
cli.py ──► cli_commands.py ──┬──► picture_analyzer.py ──┬──► config.py
                             │                          ├──► prompts.py
                             │                          ├──► metadata_manager.py ──┬──► exif_handler.py
                             │                          │                          ├──► xmp_handler.py
                             │                          │                          └──► geolocation.py
                             │                          └──► openai (SDK)
                             ├──► picture_enhancer.py ──► enhancement_filters.py
                             ├──► slide_restoration.py
                             ├──► report_generator.py
                             └──► config.py

run_description_editor.py ──► description_editor_app.py (Flask, standalone)
```

---

## 2. Proposed Architecture

### 2.1 Core Principles

1. **Plugin-based providers** — AI backends, geocoders, metadata writers, enhancement engines are all swappable
2. **Configuration-driven** — every hardcoded value becomes configurable with sensible defaults
3. **Pipeline pattern** — image processing is a composable pipeline of steps
4. **Dependency injection** — components receive their dependencies, never instantiate them
5. **Proper Python package** — installable via `pip install -e .`

### 2.2 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLI / Web UI Layer                          │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │   CLI (click) │  │  Flask Web UI    │  │  Future: REST API    │  │
│  └──────┬───────┘  └────────┬─────────┘  └──────────┬───────────┘  │
│         └──────────────┬────┴───────────────────────┘              │
│                        ▼                                           │
│              ┌─────────────────┐                                   │
│              │  Pipeline Engine │  ← orchestrates steps            │
│              └────────┬────────┘                                   │
│         ┌─────────────┼──────────────────┐                         │
│         ▼             ▼                  ▼                         │
│  ┌─────────────┐ ┌──────────┐  ┌────────────────┐                 │
│  │  Analyzers   │ │ Enhancers│  │ Metadata Writers│                │
│  │  (providers) │ │(pipeline)│  │   (providers)   │                │
│  └──────┬──────┘ └────┬─────┘  └───────┬────────┘                 │
│         │             │                │                           │
│  ┌──────┴──────┐ ┌────┴─────┐  ┌───────┴────────┐                 │
│  │ OpenAI      │ │ PIL-based│  │ EXIF (piexif)   │                │
│  │ Ollama      │ │ NumPy    │  │ XMP (xml)       │                │
│  │ Azure       │ │ OpenCV   │  │ IPTC (future)   │                │
│  │ Anthropic   │ │ Profiles │  │ Sidecar (.json) │                │
│  └─────────────┘ └──────────┘  └────────────────┘                 │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Shared Services                            │  │
│  │  ┌──────────┐ ┌───────────┐ ┌────────┐ ┌──────────────────┐  │  │
│  │  │ Geocoder │ │  Config   │ │ Cache  │ │ Event/Progress   │  │  │
│  │  │(provider)│ │ (layered) │ │(store) │ │    Bus           │  │  │
│  │  └──────────┘ └───────────┘ └────────┘ └──────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Package Structure

```
picture-analyzer/
├── pyproject.toml                    # Package definition, entry points, deps
├── README.md
├── LICENSE
├── .env.example                      # Documented env template
│
├── src/
│   └── picture_analyzer/
│       ├── __init__.py               # Package version, public API
│       ├── __main__.py               # `python -m picture_analyzer`
│       │
│       ├── config/
│       │   ├── __init__.py
│       │   ├── settings.py           # Pydantic Settings model (layered config)
│       │   ├── defaults.py           # All default values in one place
│       │   └── profiles.yaml         # Slide restoration profiles (data, not code)
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── pipeline.py           # Pipeline engine / orchestrator
│       │   ├── models.py             # Pydantic data models (AnalysisResult, Enhancement, etc.)
│       │   ├── interfaces.py         # Abstract base classes / Protocols
│       │   └── events.py             # Progress reporting, event bus
│       │
│       ├── analyzers/
│       │   ├── __init__.py
│       │   ├── base.py               # AnalyzerProtocol
│       │   ├── openai_analyzer.py    # OpenAI Vision implementation
│       │   ├── ollama_analyzer.py    # Local Ollama implementation
│       │   └── prompt_builder.py     # Composable prompt construction
│       │
│       ├── enhancers/
│       │   ├── __init__.py
│       │   ├── base.py               # EnhancerProtocol
│       │   ├── ai_enhancer.py        # Enhancement from AI recommendations
│       │   ├── profile_restorer.py   # Slide restoration profiles
│       │   ├── filters/
│       │   │   ├── __init__.py
│       │   │   ├── brightness.py
│       │   │   ├── color.py
│       │   │   ├── sharpness.py
│       │   │   └── advanced.py       # NumPy-accelerated filters
│       │   └── profiles/             # YAML profile definitions
│       │       ├── faded.yaml
│       │       ├── color_cast.yaml
│       │       └── custom/           # User-defined profiles
│       │
│       ├── metadata/
│       │   ├── __init__.py
│       │   ├── base.py               # MetadataWriterProtocol
│       │   ├── exif_writer.py
│       │   ├── xmp_writer.py
│       │   ├── manager.py            # Facade / composite writer
│       │   ├── translations/
│       │   │   ├── en.yaml
│       │   │   ├── nl.yaml
│       │   │   ├── de.yaml
│       │   │   └── fr.yaml
│       │   └── field_mappings.yaml   # EXIF tag ↔ field name mappings
│       │
│       ├── geo/
│       │   ├── __init__.py
│       │   ├── base.py               # GeocoderProtocol
│       │   ├── nominatim.py          # OSM Nominatim implementation
│       │   ├── google.py             # Future: Google Maps Geocoding
│       │   └── cache.py              # Geocoding cache (pluggable backend)
│       │
│       ├── reporting/
│       │   ├── __init__.py
│       │   ├── base.py               # ReporterProtocol
│       │   ├── markdown.py           # Markdown report generator
│       │   ├── html.py               # Future: HTML gallery
│       │   └── templates/            # Jinja2 templates for reports
│       │       ├── report.md.j2
│       │       └── gallery.md.j2
│       │
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── app.py                # Click-based CLI application
│       │   ├── commands/
│       │   │   ├── __init__.py
│       │   │   ├── analyze.py
│       │   │   ├── enhance.py
│       │   │   ├── report.py
│       │   │   └── describe.py       # Launch description editor
│       │   └── formatters.py         # CLI output formatting / progress bars
│       │
│       └── web/
│           ├── __init__.py
│           ├── app.py                # Flask app factory
│           ├── routes.py             # API endpoints
│           ├── static/
│           │   ├── index.html
│           │   ├── style.css
│           │   └── app.js
│           └── templates/            # Optional Jinja templates
│
├── profiles/                         # User-customizable slide profiles
│   └── README.md                     # How to create custom profiles
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_models.py
│   │   ├── test_pipeline.py
│   │   ├── test_prompt_builder.py
│   │   ├── test_enhancers.py
│   │   ├── test_filters.py
│   │   ├── test_exif_writer.py
│   │   ├── test_geocoder.py
│   │   └── test_report.py
│   ├── integration/
│   │   ├── test_analyze_flow.py
│   │   └── test_batch_process.py
│   └── fixtures/
│       ├── sample_analysis.json
│       └── test_image.jpg
│
└── docs/
    ├── configuration.md
    ├── custom-profiles.md
    ├── adding-providers.md
    └── api-reference.md
```

---

## 4. Design Decisions & Alternatives

### Decision 1: Configuration System

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Pydantic Settings** ✅ | Typed config model with env/file/CLI layering | Type validation, IDE support, env+file+CLI layering, `.env` support built-in, nested models | Adds `pydantic-settings` dependency |
| B. dataclasses + dotenv | Stdlib dataclasses with manual env loading | No extra deps, simple | No validation, no layering, manual type coercion |
| C. dynaconf | Third-party config library | Multiple format support, environments | Heavy dependency, learning curve |
| D. YAML/TOML file only | Config file parsed at startup | Human-readable, versionable | No env var override, no CLI override |
| E. Click context | CLI params passed through context | Works with Click | Only for CLI usage, not for library/web |

**Choice: A (Pydantic Settings)**
**Rationale:** Already using Pydantic transitively via `openai` SDK. Pydantic Settings gives typed validation, `.env` loading, env var overrides, and nested config models with zero new transitive deps. Supports layered config: defaults → config file → env vars → CLI args.

---

### Decision 2: CLI Framework

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Click** ✅ | Decorator-based CLI framework | Composable commands/groups, great help generation, parameter types, widely adopted | Extra dependency |
| B. argparse (current) | Stdlib argument parser | Zero deps, familiar | Verbose, poor subcommand UX, no plugins |
| C. Typer | Click wrapper with type hints | Modern, less boilerplate than Click | Extra dep on top of Click, newer/smaller community |
| D. Fire | Auto-generate CLI from functions | Minimal code | Poor help messages, magic behavior |

**Choice: A (Click)**
**Rationale:** Enables plugin-based command registration, has rich parameter types, integrates naturally with the provider pattern. Typer is appealing but adds an extra layer. Click is the standard for production Python CLIs.

---

### Decision 3: AI Provider Architecture

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Protocol + Registry** ✅ | `AnalyzerProtocol` with provider registry | Fully pluggable, testable with mocks, supports multiple backends | Slightly more boilerplate |
| B. Strategy pattern (class hierarchy) | ABC with concrete subclasses | Simple OOP, clear contracts | Rigid hierarchy, harder to compose |
| C. LiteLLM wrapper | Use LiteLLM to abstract all providers | One interface for 100+ models | Heavy dependency, hides provider-specific features |
| D. Direct SDK calls (current) | Hardcoded `openai.OpenAI()` | Simplest | Zero extensibility |

**Choice: A (Protocol + Registry)**
**Rationale:** Python's `Protocol` (structural subtyping) allows any conforming class to be used without inheritance. A registry pattern (`analyzer = registry.get("openai")`) makes it configuration-driven. This also enables a future Ollama/local-model provider for offline use, and makes testing trivial with mock analyzers.

```python
# Example interface
class AnalyzerProtocol(Protocol):
    def analyze(self, image_path: Path, context: AnalysisContext) -> AnalysisResult: ...

# Registry
ANALYZERS: dict[str, type[AnalyzerProtocol]] = {
    "openai": OpenAIAnalyzer,
    "ollama": OllamaAnalyzer,
}
```

---

### Decision 4: Prompt Management

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Composable Prompt Builder** ✅ | Builder pattern with sections that can be enabled/disabled/overridden | Flexible, testable, sections configurable | More complex than a string |
| B. Jinja2 templates | Prompt as a template file | Familiar, separates prompt from code | Requires template engine, harder to test logic |
| C. Single string (current) | One massive f-string | Simple | Rigid, untestable, no customization |
| D. YAML/JSON prompt definition | Structured prompt sections in data files | Versionable, overridable | Complex parsing, loses readability |

**Choice: A (Composable Prompt Builder)**
**Rationale:** Different use cases need different prompt sections. A builder allows enabling/disabling sections (e.g., skip slide profile detection for modern photos, add custom instructions per-directory). Sections are individually testable.

```python
prompt = PromptBuilder() \
    .add_section("metadata_extraction", enabled=True) \
    .add_section("location_detection", enabled=True) \
    .add_section("slide_profile", enabled=config.detect_slide_profiles) \
    .add_section("enhancement_recommendations", enabled=config.recommend_enhancements) \
    .set_language(config.metadata_language) \
    .set_context(description_text) \
    .build()
```

---

### Decision 5: Image Enhancement Architecture

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Filter Pipeline** ✅ | Chain of filter objects, each with `apply(image) → image` | Composable, orderable, individually testable, new filters = new class | Slight overhead per step |
| B. Single function (current) | One big method with if/else per adjustment | Simple | Untestable, rigid, no reordering |
| C. NumPy vectorized ops | All filters as NumPy array operations | Fast | Requires NumPy dependency, different programming model |
| D. OpenCV-based | Use cv2 for all image ops | Very fast, battle-tested | Heavy C dependency, different color model (BGR) |

**Choice: A (Filter Pipeline) with optional NumPy acceleration**
**Rationale:** The pipeline pattern makes filters composable and independently testable. Each filter is a small class with `apply(image, params) → image`. NumPy can be used inside individual filters for performance without forcing it on the architecture. OpenCV is overkill for this project's needs.

```python
pipeline = FilterPipeline([
    BrightnessFilter(factor=1.3),
    ContrastFilter(factor=1.2),
    ColorTemperatureFilter(kelvin=5800),
    UnsharpMaskFilter(radius=2, percent=150),
])
result = pipeline.apply(source_image)
```

---

### Decision 6: Geocoding Provider

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Protocol + Cache layer** ✅ | `GeocoderProtocol` with decorator-based caching | Swappable backends, transparent caching | More code |
| B. Nominatim only (current) | Direct Nominatim calls with file cache | Simple, free | Single point of failure, rate limited |
| C. geopy library | Abstraction over multiple geocoding services | Many providers built-in | Extra dependency, may be more than needed |
| D. Google Maps API | Use Google's geocoding | Most accurate | Costs money, requires API key |

**Choice: A (Protocol + Cache layer)**
**Rationale:** Keep Nominatim as default (free, no API key), but allow swapping to Google/Mapbox for higher accuracy when needed. Cache layer is a separate concern that wraps any geocoder.

---

### Decision 7: Data Models

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Pydantic models** ✅ | Typed data classes with validation and serialization | JSON serialization built-in, validation, IDE support | Already a transitive dependency |
| B. dataclasses | Stdlib data classes | No deps | Manual JSON serialization, no validation |
| C. TypedDict | Dict with type hints | Lightweight, backward compatible | No validation, no methods |
| D. Plain dicts (current) | Untyped dicts everywhere | Zero overhead | No IDE support, no validation, runtime KeyErrors |

**Choice: A (Pydantic models)**
**Rationale:** Analysis results are currently untyped dicts passed between modules. Pydantic gives validation, serialization, and IDE support. Already a transitive dependency via `openai`.

```python
class AnalysisResult(BaseModel):
    title: str
    description: str
    location: LocationInfo | None
    people: list[str]
    era: EraInfo | None
    enhancement_recommendations: list[Enhancement]
    slide_profile: SlideProfile | None
    confidence_scores: dict[str, int]
    raw_response: dict[str, Any]  # preserve original AI output
```

---

### Decision 8: Metadata Translation

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. YAML translation files** ✅ | One YAML file per language with field label translations | Easy to add languages, no code changes, community-contributable | YAML parsing at startup |
| B. Hardcoded dicts (current) | `if lang == 'nl': ...` in `exif_handler.py` | Simple | Adding a language = editing source code |
| C. gettext / i18n framework | Standard Python internationalization | Industry standard, plural forms | Overkill for field labels, complex toolchain |
| D. JSON translation files | Same as A but JSON | No YAML dep | Less human-readable for translators |

**Choice: A (YAML translation files)**
**Rationale:** Adding a new language should be "drop a YAML file in `translations/`" — no code changes. YAML is already parsed by PyYAML (add as optional dep) and is more readable than JSON for translators.

```yaml
# translations/nl.yaml
language_name: "Nederlands"
fields:
  title: "Titel"
  description: "Beschrijving"
  location: "Locatie"
  people: "Personen"
  objects: "Objecten"
  era: "Tijdperk"
  mood: "Stemming"
  time_of_day: "Moment van de dag"
```

---

### Decision 9: Slide Restoration Profiles

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. YAML profile files** ✅ | Each profile is a YAML file with adjustment parameters | User-extendable, no code changes, shareable | YAML parsing |
| B. Hardcoded dict (current) | `PROFILES = {...}` in `slide_restoration.py` | Simple | Adding a profile = editing source |
| C. JSON profiles | Same as A but JSON | No YAML dep | Less readable |
| D. Python plugin files | Each profile is a `.py` file | Maximum flexibility | Security risk, complexity |

**Choice: A (YAML profile files)**
**Rationale:** Profiles are pure data (numeric adjustment parameters). YAML makes them readable, editable by non-developers, and shareable.

```yaml
# profiles/faded.yaml
name: "Faded Slide"
description: "For slides with significant color fading"
adjustments:
  saturation: 1.5
  contrast: 1.6
  brightness: 1.15
  sharpness: 1.2
  color_balance:
    red: 1.0
    green: 1.05
    blue: 1.15
  denoise: true
  denoise_radius: 0.5
```

---

### Decision 10: Report Generation

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Jinja2 templates** ✅ | Markdown/HTML templates with Jinja2 | Customizable output, separation of logic/presentation, multiple formats | Extra dependency |
| B. String concatenation (current) | Python f-strings building markdown | Simple | Rigid, hard to customize, mixing logic and presentation |
| C. Mako templates | Alternative template engine | Fast | Less popular, different syntax |
| D. Mustache/Handlebars | Logic-less templates | Simple, portable | Limited logic, may need workarounds |

**Choice: A (Jinja2 templates)**
**Rationale:** Users may want to customize report format. Jinja2 is the standard Python template engine, supports template inheritance, and works for both Markdown and HTML output.

---

### Decision 11: Web UI Architecture

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Flask + vanilla JS (current, improved)** ✅ | Flask API backend, single HTML+JS frontend | Simple, no build step, works now | Limited interactivity for complex UIs |
| B. Flask + htmx | Server-rendered with htmx for interactivity | No JS framework, progressive enhancement | Less common, learning curve |
| C. FastAPI + React/Vue SPA | Modern API + SPA frontend | Rich UX, async support | Build toolchain, much heavier |
| D. Streamlit | Rapid data app framework | Very fast to build | Limited customization, Streamlit-specific |
| E. Gradio | ML-focused web UI | Great for AI apps | Limited customization |

**Choice: A (Flask + vanilla JS, improved)**
**Rationale:** The web UI is a secondary feature (description editing). Keeping it simple with Flask and vanilla JS avoids a build toolchain. The current implementation works — it just needs proper static file serving and format support fixes. If the UI grows in scope, htmx would be a natural next step.

---

### Decision 12: Testing Strategy

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. pytest + fixtures + mocks** ✅ | pytest with conftest fixtures, mock AI responses | Fast, isolated, comprehensive | Need to maintain fixtures |
| B. unittest | Stdlib test framework | No deps | Verbose, less ergonomic |
| C. Integration tests only | Test full pipelines with real images | Tests real behavior | Slow, requires API keys, flaky |

**Choice: A (pytest + fixtures + mocks)**
**Rationale:** Unit tests with mocked AI responses test all logic without API calls. Integration tests run optionally with real API keys. pytest is the Python standard.

---

### Decision 13: Dependency Injection Approach

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A. Constructor injection** ✅ | Dependencies passed via `__init__` | Simple, explicit, testable | Some wiring boilerplate |
| B. DI container (dependency-injector) | Framework-managed injection | Automatic wiring, scopes | Heavy framework, learning curve |
| C. Module-level singletons (current) | Import and use global instances | Zero boilerplate | Untestable, tight coupling |
| D. Service locator | Central registry of services | Flexible | Hidden dependencies, anti-pattern |

**Choice: A (Constructor injection)**
**Rationale:** Simple and explicit. A `create_app()` or `build_pipeline()` factory wires everything together. No framework needed.

```python
def build_pipeline(config: Settings) -> Pipeline:
    analyzer = OpenAIAnalyzer(api_key=config.openai.api_key, model=config.openai.model)
    geocoder = CachedGeocoder(NominatimGeocoder(), cache_path=config.geo.cache_path)
    enhancer = AIEnhancer(filters=FilterPipeline.default())
    metadata_writer = CompositeMetadataWriter([
        ExifWriter(language=config.metadata.language),
        XmpWriter(),
    ])
    return Pipeline(analyzer, geocoder, enhancer, metadata_writer, config)
```

---

## 5. Tradeoff Matrix

### 5.1 Overall Architecture Tradeoffs

| Quality Attribute | Current | Proposed | Tradeoff |
|---|---|---|---|
| **Extensibility** | ⭐ Low — every extension requires source edits | ⭐⭐⭐⭐⭐ High — plugins, providers, YAML configs | More initial structure to set up |
| **Simplicity** | ⭐⭐⭐⭐ High — flat files, direct calls | ⭐⭐⭐ Medium — more files, more abstractions | Learning curve for contributors |
| **Testability** | ⭐ Low — tight coupling, no tests | ⭐⭐⭐⭐⭐ High — interfaces, DI, mocks | Must write and maintain tests |
| **Performance** | ⭐⭐ Low — pure Python pixels | ⭐⭐⭐⭐ High — optional NumPy, pipeline | Optional NumPy dependency |
| **Reliability** | ⭐⭐ Medium — silent failures | ⭐⭐⭐⭐ High — typed models, validation | Stricter errors may surprise users initially |
| **Onboarding** | ⭐⭐⭐⭐ Easy — read one file | ⭐⭐⭐ Medium — understand package structure | Good docs mitigate this |
| **Maintainability** | ⭐⭐ Low — changes ripple | ⭐⭐⭐⭐⭐ High — isolated modules | More files to navigate |
| **Deployment** | ⭐⭐ Manual — copy files | ⭐⭐⭐⭐⭐ High — `pip install`, entry points | Packaging setup required |

### 5.2 Decision Tradeoff Comparison

| Decision | Chosen | Runner-up | Why chosen over runner-up |
|---|---|---|---|
| Config system | Pydantic Settings | dataclasses + dotenv | Validation + layering worth the (zero) extra dep cost |
| CLI framework | Click | Typer | More mature, no extra layer, plugin-friendly |
| AI providers | Protocol + Registry | LiteLLM | Lighter, no dependency on LiteLLM's update cycle |
| Prompts | Composable Builder | Jinja2 templates | Prompts need logic (conditional sections), not just templating |
| Enhancement | Filter Pipeline | NumPy vectorized | Pipeline is the architecture; NumPy is an implementation detail inside filters |
| Geocoding | Protocol + Cache | geopy | Simpler, fewer deps, we only need forward geocoding |
| Data models | Pydantic | dataclasses | Already transitive dep, validation is critical for AI output parsing |
| Translations | YAML files | gettext | Field labels don't need plural forms or complex i18n |
| Profiles | YAML files | JSON | More readable for the target data (nested numbers + descriptions) |
| Reports | Jinja2 | String concat | Separation of template from logic is essential for customization |
| Web UI | Flask + vanilla JS | FastAPI + SPA | Proportional to the feature's importance |
| Testing | pytest | unittest | Industry standard, better fixtures, less verbose |
| DI approach | Constructor injection | DI container | Simplicity — this project doesn't need a container |

### 5.3 Dependency Cost Analysis

| New Dependency | Why | Size Impact | Alternative if rejected |
|---|---|---|---|
| `click` | CLI framework | ~200KB | Stay with argparse (lose composability) |
| `pydantic-settings` | Config management | ~50KB (pydantic already transitive) | Manual env parsing |
| `PyYAML` | Profiles, translations | ~500KB | Use JSON (less readable) |
| `Jinja2` | Report templates | ~800KB (already dep of Flask) | Keep string concatenation |
| `numpy` (optional) | Fast image filters | ~30MB | Keep pure Python (slow for large images) |
| `rich` (optional) | Pretty CLI output | ~1MB | Plain print statements |

**Total new required deps:** `click` + `PyYAML` = ~700KB
**Already transitive:** `pydantic-settings` (via pydantic), `Jinja2` (via Flask)
**Optional:** `numpy`, `rich`

---

## 6. Configuration System

### 6.1 Layered Configuration (Priority: highest wins)

```
CLI arguments          ← highest priority (--model gpt-4o)
  ↓
Environment variables  ← OPENAI_MODEL=gpt-4o
  ↓
.env file              ← OPENAI_MODEL=gpt-4o-mini
  ↓
Config file            ← config.yaml in project root
  ↓
Defaults               ← hardcoded sensible defaults (lowest priority)
```

### 6.2 Proposed Configuration Model

```python
class OpenAIConfig(BaseSettings):
    api_key: SecretStr
    model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    detail: str = "auto"            # "auto", "low", "high"

class GeoConfig(BaseSettings):
    provider: str = "nominatim"     # "nominatim", "google", "none"
    cache_path: Path = Path(".geocoding_cache.json")
    cache_enabled: bool = True
    confidence_threshold: int = 80  # 0-100
    user_agent: str = "picture-analyzer/1.0"
    timeout_seconds: int = 5
    # Google-specific
    google_api_key: SecretStr | None = None

class MetadataConfig(BaseSettings):
    language: str = "en"
    write_exif: bool = True
    write_xmp: bool = True
    write_gps: bool = True
    jpeg_quality: int = 95
    description_max_length: int = 16000

class EnhancementConfig(BaseSettings):
    enabled: bool = True
    jpeg_quality: int = 95
    color_temperature_baseline: int = 6500  # Kelvin

class SlideRestorationConfig(BaseSettings):
    enabled: bool = True
    profiles_dir: Path = Path("profiles")
    auto_detect: bool = True
    confidence_threshold: int = 50
    jpeg_quality: int = 95

class WebConfig(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 7000
    debug: bool = True
    description_template_path: Path | None = None

class OutputConfig(BaseSettings):
    directory: Path = Path("output")
    temp_directory: Path = Path("tmp")
    naming_pattern: str = "{stem}_analyzed{suffix}"  # supports: stem, suffix, date, counter
    enhanced_pattern: str = "{stem}_enhanced{suffix}"
    restored_pattern: str = "{stem}_restored_{profile}{suffix}"
    thumbnails_dir: str = "thumbnails"
    thumbnail_size: int = 150
    thumbnail_quality: int = 85
    cleanup_temp: bool = True

class ReportConfig(BaseSettings):
    template: str = "default"       # template name or path
    format: str = "markdown"        # "markdown", "html"
    include_thumbnails: bool = True
    thumbnail_max_size: int = 300
    base64_thumbnails: bool = True

class PromptConfig(BaseSettings):
    detect_slide_profiles: bool = True
    recommend_enhancements: bool = True
    detect_location: bool = True
    detect_people: bool = True
    detect_era: bool = True
    custom_instructions: str | None = None  # appended to prompt

class Settings(BaseSettings):
    openai: OpenAIConfig
    geo: GeoConfig = GeoConfig()
    metadata: MetadataConfig = MetadataConfig()
    enhancement: EnhancementConfig = EnhancementConfig()
    slide_restoration: SlideRestorationConfig = SlideRestorationConfig()
    web: WebConfig = WebConfig()
    output: OutputConfig = OutputConfig()
    report: ReportConfig = ReportConfig()
    prompt: PromptConfig = PromptConfig()
    
    supported_formats: set[str] = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic'}
    batch_size: int = 5
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_prefix="PA_",                # PA_OPENAI__MODEL=gpt-4o
        env_nested_delimiter="__",
        env_file=".env",
        yaml_file="config.yaml",         # optional config file
    )
```

### 6.3 Example `config.yaml`

```yaml
openai:
  model: "gpt-4o-mini"
  max_tokens: 4096

geo:
  provider: "nominatim"
  confidence_threshold: 80

metadata:
  language: "nl"
  jpeg_quality: 95

enhancement:
  color_temperature_baseline: 6500

slide_restoration:
  profiles_dir: "./profiles"
  confidence_threshold: 50

output:
  directory: "./output"
  naming_pattern: "{stem}_analyzed{suffix}"
  enhanced_pattern: "{stem}_enhanced{suffix}"
  restored_pattern: "{stem}_restored_{profile}{suffix}"

prompt:
  detect_slide_profiles: true
  recommend_enhancements: true
  custom_instructions: null

web:
  port: 7000

batch_size: 5
log_level: "INFO"
```

### 6.4 Example `.env` overrides

```bash
# Required
OPENAI_APIKEY=sk-...

# Optional overrides (PA_ prefix + double underscore for nesting)
PA_OPENAI__MODEL=gpt-4o
PA_METADATA__LANGUAGE=nl
PA_GEO__CONFIDENCE_THRESHOLD=70
PA_OUTPUT__DIRECTORY=./my-output
PA_WEB__PORT=8080
PA_LOG_LEVEL=DEBUG
```

---

## 7. Plugin / Provider Architecture

### 7.1 Core Protocols

```python
from typing import Protocol, runtime_checkable
from pathlib import Path
from .models import AnalysisResult, AnalysisContext, GeoLocation, ImageData

@runtime_checkable
class Analyzer(Protocol):
    """Analyzes an image and returns structured metadata."""
    def analyze(self, image: ImageData, context: AnalysisContext) -> AnalysisResult: ...

@runtime_checkable
class Geocoder(Protocol):
    """Converts location names to GPS coordinates."""
    def geocode(self, location: str) -> GeoLocation | None: ...

@runtime_checkable
class MetadataWriter(Protocol):
    """Writes metadata to an image file."""
    def write(self, image_path: Path, analysis: AnalysisResult) -> bool: ...

@runtime_checkable
class ImageFilter(Protocol):
    """Applies a single transformation to an image."""
    def apply(self, image: Image.Image) -> Image.Image: ...
    @property
    def name(self) -> str: ...

@runtime_checkable
class Reporter(Protocol):
    """Generates reports from analysis results."""
    def generate(self, results: list[AnalysisResult], output_path: Path) -> Path: ...
```

### 7.2 Provider Registration

```python
# Analyzers register themselves
from picture_analyzer.core.registry import registry

@registry.register("analyzer", "openai")
class OpenAIAnalyzer:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", **kwargs): ...
    def analyze(self, image: ImageData, context: AnalysisContext) -> AnalysisResult: ...

@registry.register("analyzer", "ollama")
class OllamaAnalyzer:
    def __init__(self, model: str = "llava", base_url: str = "http://localhost:11434", **kwargs): ...
    def analyze(self, image: ImageData, context: AnalysisContext) -> AnalysisResult: ...

# Usage
analyzer = registry.create("analyzer", config.openai.provider, **config.openai.dict())
```

### 7.3 Adding a New Provider (Developer Experience)

To add a new AI provider, a developer would:

1. Create `src/picture_analyzer/analyzers/my_provider.py`
2. Implement the `Analyzer` protocol
3. Register with `@registry.register("analyzer", "my_provider")`
4. Set `PA_OPENAI__PROVIDER=my_provider` in config

No existing code is modified.

---

## 8. Data Flow & Pipeline

### 8.1 Processing Pipeline

```
Input                 Analysis              Enhancement           Metadata             Output
──────────           ──────────            ─────────────         ──────────           ──────────

                     ┌─────────┐
                     │ Read    │
 source.jpg ────────►│ desc.txt├──► context
                     └─────────┘       │
                                       ▼
                     ┌─────────────────────┐
                     │   AI Analyzer       │
                     │ (OpenAI/Ollama/...) │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │   AnalysisResult    │◄──── Pydantic model
                     │   (structured data) │
                     └──┬──────┬───────┬───┘
                        │      │       │
              ┌─────────┘      │       └─────────────┐
              ▼                ▼                      ▼
     ┌────────────┐  ┌────────────────┐    ┌──────────────────┐
     │  Geocoder  │  │  AI Enhancer   │    │ Profile Restorer │
     │(Nominatim) │  │(filter pipeline)│   │ (YAML profiles)  │
     └─────┬──────┘  └───────┬────────┘    └────────┬─────────┘
           │                 │                      │
           ▼                 ▼                      ▼
     ┌──────────┐    ┌──────────────┐       ┌─────────────────┐
     │ GPS data │    │ _enhanced.jpg│       │ _restored_*.jpg │
     └────┬─────┘    └──────────────┘       └─────────────────┘
          │
          ▼
    ┌───────────────────┐
    │  Metadata Writers │
    │  (EXIF + XMP)     │
    │  + GPS embed      │
    └─────────┬─────────┘
              │
              ▼
    ┌───────────────────┐
    │  _analyzed.jpg    │  ← source + metadata embedded
    │  _analyzed.json   │  ← analysis data
    └───────────────────┘
              │
              ▼
    ┌───────────────────┐
    │  Report Generator │
    │  (Jinja2 template)│
    └─────────┬─────────┘
              ▼
    ┌───────────────────┐
    │  report.md / .html│
    └───────────────────┘
```

### 8.2 Pipeline Configuration

```python
# Each step is optional and configurable
pipeline_config:
  steps:
    - analyze:        { enabled: true, provider: "openai" }
    - geocode:        { enabled: true, provider: "nominatim" }
    - enhance:        { enabled: true }
    - restore:        { enabled: true, profile: "auto" }
    - write_metadata: { enabled: true, formats: ["exif", "xmp"] }
    - save_json:      { enabled: true }
    - report:         { enabled: false }
```

---

## 9. Hardcoded Values Inventory

Every hardcoded value in the current codebase, mapped to its proposed configuration path:

### 9.1 AI & API

| Current Hardcoded Value | File | Proposed Config Path | Default |
|---|---|---|---|
| `gpt-4o-mini` | `config.py` | `openai.model` | `gpt-4o-mini` |
| `4096` (max_tokens) | `picture_analyzer.py` | `openai.max_tokens` | `4096` |
| `auto` (detail level) | `picture_analyzer.py` | `openai.detail` | `auto` |

### 9.2 Image Processing

| Current Hardcoded Value | File | Proposed Config Path | Default |
|---|---|---|---|
| `95` (JPEG quality) | 6+ files | `metadata.jpeg_quality` / `enhancement.jpeg_quality` | `95` |
| `6500` (color temp baseline) | `prompts.py`, `picture_enhancer.py`, `enhancement_filters.py` | `enhancement.color_temperature_baseline` | `6500` |
| `1500–15000` (Kelvin clamp) | `picture_enhancer.py` | `enhancement.kelvin_range` | `[1500, 15000]` |
| `0.1–2.5` (channel factor clamp) | `picture_enhancer.py` | `enhancement.channel_factor_range` | `[0.1, 2.5]` |
| `2, 150, 3` (USM defaults) | `picture_enhancer.py` | `enhancement.unsharp_mask_defaults` | `{radius: 2, percent: 150, threshold: 3}` |
| `0.5` (denoise blur radius) | `slide_restoration.py` | `slide_restoration.denoise_radius` | `0.5` |

### 9.3 Geocoding

| Current Hardcoded Value | File | Proposed Config Path | Default |
|---|---|---|---|
| `picture-analyzer/1.0` (User-Agent) | `geolocation.py` | `geo.user_agent` | `picture-analyzer/1.0` |
| `5` (timeout seconds) | `geolocation.py` | `geo.timeout_seconds` | `5` |
| `.geocoding_cache.json` | `geolocation.py` | `geo.cache_path` | `.geocoding_cache.json` |
| `80` (GPS confidence) | `config.py` | `geo.confidence_threshold` | `80` |
| Vague terms blocklist | `geolocation.py` | `geo.vague_terms` | `[list in defaults.py]` |

### 9.4 Metadata

| Current Hardcoded Value | File | Proposed Config Path | Default |
|---|---|---|---|
| `en` / `nl` translations | `exif_handler.py` | `metadata.language` + `translations/{lang}.yaml` | `en` |
| `16000` (description max length) | `exif_handler.py` | `metadata.description_max_length` | `16000` |
| `(2, 3, 0, 0)` (GPS version) | `exif_handler.py` | `metadata.gps_version` | `(2, 3, 0, 0)` |
| `WGS-84` (GPS datum) | `exif_handler.py` | `metadata.gps_datum` | `WGS-84` |
| XMP namespace URIs | `xmp_handler.py` | `metadata.xmp_namespace` | Current URIs |

### 9.5 Output & Naming

| Current Hardcoded Value | File | Proposed Config Path | Default |
|---|---|---|---|
| `output` (default dir) | `config.py` | `output.directory` | `output` |
| `tmp` (temp dir) | `config.py` | `output.temp_directory` | `tmp` |
| `_analyzed` suffix | `cli_commands.py` | `output.naming_pattern` | `{stem}_analyzed{suffix}` |
| `_enhanced` suffix | `cli_commands.py` | `output.enhanced_pattern` | `{stem}_enhanced{suffix}` |
| `_restored_` suffix | `cli_commands.py` | `output.restored_pattern` | `{stem}_restored_{profile}{suffix}` |
| `thumbnails` subdir | `config.py` | `output.thumbnails_dir` | `thumbnails` |
| `150` (thumb size) | `config.py` | `output.thumbnail_size` | `150` |
| `85` (thumb quality) | `config.py` | `output.thumbnail_quality` | `85` |

### 9.6 Slide Restoration Profiles

| Current Hardcoded Value | File | Proposed Config Path | Default |
|---|---|---|---|
| All 6 profile dicts | `slide_restoration.py` | `profiles/*.yaml` | Individual YAML files |
| `50` (profile confidence) | `cli_commands.py` | `slide_restoration.confidence_threshold` | `50` |

### 9.7 Web UI

| Current Hardcoded Value | File | Proposed Config Path | Default |
|---|---|---|---|
| `7000` (port) | `description_editor_app.py`, `run_description_editor.py` | `web.port` | `7000` |
| `127.0.0.1` (host) | Flask default | `web.host` | `127.0.0.1` |
| `True` (debug mode) | `description_editor_app.py` | `web.debug` | `true` (dev) / `false` (prod) |
| `200` (thumb size) | `description_editor_app.py` | `web.thumbnail_size` | `200` |
| `PNG` (thumb format) | `description_editor_app.py` | `web.thumbnail_format` | `PNG` |
| Dutch template | `description_editor_app.py` | `web.description_template_path` | Loaded from file based on language |
| `*.JPG` / `*.jpg` only | `description_editor_app.py` | Use `supported_formats` from global config | All supported formats |
| `photos` (default dir) | `description_editor_app.py` | CLI argument / `web.default_photos_dir` | `.` |

### 9.8 Prompt Content

| Current Hardcoded Value | File | Proposed Config Path | Default |
|---|---|---|---|
| Enhancement keyword list | `prompts.py` | `prompt.enhancement_keywords` (or keep in prompt builder) | Current list |
| Slide profile names | `prompts.py` | Auto-generated from loaded YAML profiles | Dynamic |
| Era instructions (1950-2000) | `prompts.py` | Prompt builder section, toggleable | Enabled |
| Brightness mandate for underexposed | `prompts.py` | Prompt builder section | Enabled |

### 9.9 Language Maps

| Current Hardcoded Value | File | Proposed Config Path | Default |
|---|---|---|---|
| Language code → name map | `picture_analyzer.py` | `defaults.py` or auto-detect from `translations/` dir | Current map |
| MIME type map | `picture_analyzer.py` | `defaults.py` | Current map |

---

## 10. Migration Path

### Phase 1: Foundation (non-breaking)
1. Create `pyproject.toml` with entry points
2. Create `src/picture_analyzer/` package structure
3. Move existing files into package with compatibility imports
4. Create Pydantic Settings model with all current defaults
5. Add `config.yaml.example` and `.env.example`

### Phase 2: Core Refactoring
6. Define Protocol interfaces for all providers
7. Extract Pydantic data models from dict usage
8. Refactor `PictureAnalyzer` to use `AnalyzerProtocol`
9. Refactor geocoding to use `GeocoderProtocol`
10. Refactor metadata writing to use `MetadataWriterProtocol`

### Phase 3: Externalize Data
11. Move slide profiles to YAML files
12. Move translations to YAML files
13. Move report templates to Jinja2 files
14. Move description template to configurable file

### Phase 4: Enhancement Pipeline
15. Refactor filters into individual `ImageFilter` classes
16. Create `FilterPipeline` compositor
17. Optional: add NumPy-accelerated filter variants

### Phase 5: CLI & Web
18. Migrate CLI from argparse to Click
19. Add progress reporting (rich/click progressbar)
20. Fix web UI format support, make configurable

### Phase 6: Quality
21. Add unit tests for all modules
22. Add integration test fixtures
23. Add CI pipeline config
24. Documentation

### Estimated Effort

| Phase | Effort | Risk | Can be done incrementally? |
|---|---|---|---|
| Phase 1 | 2-3 days | Low | Yes — backward compatible |
| Phase 2 | 3-4 days | Medium | Yes — one protocol at a time |
| Phase 3 | 1-2 days | Low | Yes — one data type at a time |
| Phase 4 | 2-3 days | Low | Yes — one filter at a time |
| Phase 5 | 1-2 days | Low | Yes |
| Phase 6 | 3-5 days | Low | Yes — tests can be added incrementally |
| **Total** | **~12-19 days** | | |

---

## Appendix A: Current Bugs to Fix During Migration

| Bug | File | Fix |
|-----|------|-----|
| `analysis` variable undefined | `report_generator.py` ~L286 | Should be `result` or `analysis_data` |
| Duplicate `@staticmethod` decorator | `slide_restoration.py` | Remove duplicate |
| `metadata_config.py` imported but unused | `exif_handler.py` | Either use the mapping or remove the import |
| Web UI only globs `*.JPG/*.jpg` | `description_editor_app.py` | Use `SUPPORTED_FORMATS` from config |
| `flask` not in `requirements.txt` | `requirements.txt` | Add `flask` dependency |

## Appendix B: Future Extension Points

| Extension | How it plugs in |
|-----------|----------------|
| **Ollama/local AI** | New `AnalyzerProtocol` implementation |
| **Google Maps geocoding** | New `GeocoderProtocol` implementation |
| **Immich integration** | New CLI command + API client |
| **IPTC metadata** | New `MetadataWriterProtocol` implementation |
| **HTML gallery** | New `ReporterProtocol` implementation + Jinja2 template |
| **Batch queue (Redis/Celery)** | Wrap pipeline in task queue |
| **Custom slide profiles** | Drop YAML file in `profiles/` directory |
| **New language** | Drop YAML file in `translations/` directory |
| **Custom report format** | Drop Jinja2 template in `templates/` directory |
| **OpenCV filters** | New `ImageFilter` implementations |
