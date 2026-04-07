# Development Roadmap

## Phase 1: Core Image Analysis ✅ COMPLETED
- [x] Git repository initialization
- [x] Python project structure setup
- [x] OpenAI Vision API integration (GPT-4 Turbo with vision)
- [x] EXIF metadata reading/writing
- [x] Single image analysis with 11 metadata fields
- [x] Batch image processing
- [x] CLI tool with 5 commands (analyze, batch, enhance, process, restore-slide)
- [x] JSON output for detailed analysis results
- [x] Environment configuration with .env
- [x] Support for multiple formats (JPG, PNG, GIF, BMP, TIFF, WebP, HEIC/HEIF)

## Phase 2: Image Enhancement ✅ COMPLETED
- [x] Color correction (saturation adjustment via smart enhancement)
- [x] Contrast enhancement
- [x] Brightness adjustment
- [x] Sharpness enhancement
- [x] AI-guided enhancement from analysis recommendations
- [x] Automatic recommendation parsing and application
- [x] Smart factor calculation from percentage recommendations
- [x] EXIF preservation on enhanced images
- [x] Batch enhancement capability

## Phase 2.5: Slide Restoration ✅ COMPLETED
- [x] Specialized restoration for old slides and dia positives
- [x] 6 restoration profiles (faded, color_cast, red_cast, yellow_cast, aged, well_preserved)
- [x] Auto-detection of slide condition from analysis
- [x] 7-step restoration pipeline
- [x] Dust/speckle removal
- [x] Color balance correction
- [x] Film grain/noise reduction
- [x] Red/magenta cast correction for vintage slides
- [x] Yellow/warm cast correction
- [x] Integrated into process command
- [x] CLI command with profile selection
- [x] Comprehensive documentation (SLIDE_RESTORATION_GUIDE.md)

## Phase 2.6: Context-Aware Analysis ✅ COMPLETED
- [x] Support for description.txt files in image directories
- [x] Description context passed to AI vision model
- [x] Enhanced EXIF generation with contextual understanding
- [x] Automatic description file reading and integration
- [x] Dutch field names supported: `Datum:`, `Locatie:`, `Personen:`, `Activiteit:`, `Opmerkingen:`
- [x] Hallucination-prevention: person/activity/notes fields stripped from prompt context
- [x] `D Month YYYY` Dutch date format parsed into EXIF DateTimeOriginal

## Phase 2.7: Report Generation ✅ COMPLETED
- [x] Markdown report generation from analysis results
- [x] Summary table with numbered images and key metadata
- [x] Detailed analysis sections for each image
- [x] Description.txt content integration in reports
- [x] Image references and links in reports
- [x] Complete metadata tables (all 11 aspects)
- [x] Enhancement recommendations tables
- [x] Slide restoration profile recommendations in reports
- [x] 'report' CLI command for markdown generation
- [x] Configurable report output paths

## Phase 2.8: Local AI Model Support (Ollama) ✅ COMPLETED
- [x] OllamaAnalyzer — full drop-in for OpenAI in stepped pipeline
- [x] `llama3.2-vision:11b` tested and working (CPU and GPU)
- [x] Configurable via `config.yaml`: model, base_url, num_ctx, timeout, keep_alive
- [x] Stepped pipeline mode: separate AI call per section (metadata, location, enhancement, slide profiles)
- [x] KV-cache flush between batch images (`ollama stop` after each image) — prevents visual bleed
- [x] `repeat_penalty: 1.3` to prevent model repetition loops
- [x] Token statistics displayed per step (prompt→output tokens, tok/s)
- [x] `--skip-existing` flag to resume interrupted batch runs

## Phase 3: Advanced Features (NEXT)
- [ ] Database storage for analysis results
  - [ ] SQLite for local storage
  - [ ] Result indexing and search
  - [ ] Historical comparison
  
- [ ] Web interface
  - [ ] Flask/FastAPI backend
  - [ ] Frontend for image upload and processing
  - [ ] Real-time processing
  - [ ] Result visualization and gallery
  
- [ ] Image organization
  - [ ] Auto-tagging based on detection
  - [ ] Smart folder organization by categories
  - [ ] Advanced search functionality
  
- [ ] Performance optimization
  - [ ] Parallel batch processing (multiple images simultaneously)
  - [ ] Progress tracking for long operations

## Phase 4: AI Integration Enhancements
- [ ] Additional local model support (other Ollama-compatible models)
- [ ] Claude Vision integration
- [ ] Advanced analysis features
  - [ ] Object recognition with confidence scores
  - [ ] Text extraction (OCR)
  - [ ] Face detection and privacy blur

## Phase 5: Deployment & Distribution
- [ ] Docker containerization
- [ ] Cloud deployment options
  - [ ] AWS Lambda
  - [ ] Google Cloud Functions
  - [ ] Azure Functions
  
- [ ] API server setup
- [ ] PyPI package distribution
- [ ] Docker Hub image publishing
- [ ] Comprehensive documentation and tutorials

## Technical Debt & Maintenance
- [ ] Add comprehensive unit tests
- [ ] Add integration tests
- [ ] Improve error handling and validation
- [ ] Add logging system
- [ ] Code refactoring and optimization
- [ ] Security audit and improvements
- [ ] Performance profiling and optimization

## Completed Dependencies
- OpenAI API client ✅ (v2.14.0)
- Pillow (image processing) ✅ (v12.1.0)
- piexif (EXIF handling) ✅ (v1.1.3)
- python-dotenv (config) ✅ (v1.2.1)
- requests (HTTP) ✅ (v2.32.5)
- pillow-heif (HEIC support) ✅ (v1.1.1)

## Future Dependencies
- Flask/FastAPI (web UI) - Phase 3
- SQLAlchemy (database ORM) - Phase 3
- pytest (testing) - Phase 5
- Docker - Phase 5
- anthropic (Claude API) - Phase 4
- torch/tensorflow (local AI models) - Phase 4

## Notes
- All API keys are stored in .env (not committed to git)
- EXIF data is embedded in JPEGs; other formats are converted
- Analysis results are saved as both EXIF and JSON files
- CLI tool provides easy access for non-Python users
- Code is modular and extensible for future features
