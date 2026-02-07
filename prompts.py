"""
Prompts for image analysis
"""

ANALYSIS_PROMPT = """You are analyzing an image. 

IMPORTANT LANGUAGE RULES:
- METADATA SECTION: Respond ONLY in {language}. All text, descriptions, and metadata must be in {language}.
- ENHANCEMENT SECTION: Always respond in ENGLISH. Technical parameters and recommendations must ALWAYS be in English.

Provide DETAILED and COMPREHENSIVE analysis with thorough descriptions for all metadata fields. Be specific and descriptive.

Analyze this image and provide detailed information in two separate sections.

=== METADATA SECTION (for EXIF embedding) - RESPOND IN {language} ===
1. **Objects**: List all visible objects and items in the image
2. **Persons**: Identify if there are any people/persons visible and describe them briefly
3. **Weather**: Describe the weather conditions if visible (sunny, cloudy, rainy, etc.)
4. **Mood/Atmosphere**: Describe the mood, atmosphere, or feeling conveyed by the image
5. **Time of Day**: Estimate the time of day based on lighting (morning, afternoon, evening, night, etc.)
6. **Season/Date**: If there are any indicators, estimate the season or date period
7. **Scene Type**: Classify the type of scene (portrait, landscape, macro, wildlife, still-life, action, candid, street, architecture, food, travel, etc.)
8. **Location/Setting**: Identify where this is - indoor/outdoor, urban/rural/nature, specific environment type
9. **Activity/Action**: Describe what's happening or the main activity in the photo (if any)
10. **Photography Style**: Identify the photography style or technique (e.g., portrait photography, landscape photography, macro photography, documentary, fine art, etc.)
11. **Composition Quality**: Rate the composition quality (excellent, good, fair, needs work) and note key compositional elements (rule of thirds, leading lines, symmetry, depth, framing, etc.)

=== LOCATION DETECTION SECTION (IN {language}) ===
12. **Location Detection**: Analyze ALL visible clues to determine geographic location:
    - Visible signs, text, license plates, street markers (language, format, content)
    - Architecture style and construction materials (indicates region/country)
    - Vegetation and landscape type (climate indicators)
    - Road/infrastructure style (markings, design, materials)
    - Vehicle types and styles visible
    - Any other geographic indicators
    - Format your response as JSON: {{"country": "...", "region": "...", "city_or_area": "...", "location_type": "urban/rural/suburban/mixed", "confidence": 0-100, "reasoning": "..."}}
    - confidence: 0-100 score (100=certain, 0=complete guess)
    - Be as specific as possible while maintaining honesty about confidence
    - IMPORTANT: All location names (country, region, city) should be in {language}

=== ENHANCEMENT RECOMMENDATIONS SECTION (DETAILED & QUANTIFIABLE) - ALWAYS IN ENGLISH ===
12. **Lighting Quality Assessment**: 
    - Current state: underexposed/properly exposed/overexposed
    - Specific measurements: estimated EV adjustment needed (-1.5 to +1.5)
    - Shadow detail: crushed/normal/blown out
    - **CRITICAL**: If underexposed, MUST recommend specific brightness increase percentage in recommendations (see section 17)
    - **CRITICAL**: If overexposed, MUST recommend specific brightness decrease or highlight reduction in recommendations
    - Specific recommendation: e.g., "increase brightness by 25-30%", "reduce highlights by 15%"

13. **Color & White Balance Analysis**:
    - Dominant colors and their intensity
    - Color temperature assessment: warm (K), neutral (K), cool (K) - estimate Kelvin temperature
    - Detected color casts: none/slight warm/strong warm/slight cool/strong cool
    - Saturation level: desaturated (recommend +40-50%)/normal/oversaturated (recommend -20-30%)
    - **CRITICAL**: If warm/orange/yellow cast detected → MUST include COLOR_TEMPERATURE + RED_CHANNEL + BLUE_CHANNEL + GREEN_CHANNEL in recommendations
    - For strong orange/yellow casts (typical of 1970s-1980s film):
      * ALWAYS recommend COLOR_TEMPERATURE cool by 500-1000K
      * ALWAYS recommend RED_CHANNEL reduce by 12-18% (to desaturate oranges)
      * ALWAYS recommend BLUE_CHANNEL increase by 15-20% (to restore blue balance - ESSENTIAL!)
      * ALWAYS recommend GREEN_CHANNEL increase by 10-15% (to brighten underexposed greens)
      * ALWAYS recommend VIBRANCE increase by 15-25% (to restore cyan/green vibrancy hidden by orange)
      * Example: "COLOR_TEMPERATURE: cool by 800K", "RED_CHANNEL: reduce by 15%", "BLUE_CHANNEL: increase by 18%", "GREEN_CHANNEL: increase by 12%", "VIBRANCE: increase by 20%"
    - **REMINDER**: For ANY photo that appears to be from 1950-2000 era, automatically apply this 4-part color correction pattern. Don't skip BLUE_CHANNEL or GREEN_CHANNEL.

14. **Sharpness, Clarity & Noise**:
    - Overall sharpness: soft/slightly soft/sharp/oversharpened
    - Specific areas with blur (if any): specify location and severity
    - Noise assessment: none/minimal/moderate/high - recommend noise reduction if needed
    - Clarity recommendation: e.g., "apply unsharp mask (radius=1.5, amount=80%)", "boost local contrast by 20%"
    - Specific recommendation: e.g., "increase sharpness by 30%", "apply moderate noise reduction"

15. **Contrast Enhancement**:
    - Current contrast level: very low/low/normal/high/very high
    - Recommended adjustment: specific percentage e.g., "increase contrast by 25%"
    - Shadow/midtone/highlight adjustments if needed: e.g., "brighten shadows by 15%, boost highlights by 10%"
    - Local contrast enhancement: recommend unsharp mask or clarity boost with specific values

16. **Composition & Technical Issues**:
    - Any visible defects: dust spots, scratches, artifacts, distortion
    - Vignetting: none/slight/moderate/strong - recommend correction %
    - Chromatic aberration: none/slight/present - recommend correction approach
    - Straightness: perfectly level/slightly tilted/noticeably tilted
    - Specific fixes needed: e.g., "remove 2-3 dust spots", "correct 2-degree tilt"

17. **Recommended Enhancements** (prioritized list with specific parameters - REQUIRED FORMAT):
    - IMPORTANT: Always use this EXACT format for EVERY enhancement recommendation
    - Each line must start with: "ACTION: description with percentage or parameter"
    - If NO enhancement needed, respond: "NO_ENHANCEMENTS: maintain current quality"
    - **MANDATORY: BRIGHTNESS ADJUSTMENT FOR EXPOSURE**
      * If image is underexposed: ALWAYS include "BRIGHTNESS: increase by X%" (typically 15-40% for dark images, more for very dark)
      * If image is overexposed: ALWAYS include "BRIGHTNESS: decrease by X%" or reduce highlights
      * Calculate brightness increase needed based on EV adjustment: roughly 1 EV = 25-30% brightness increase
      * For very dark/underexposed images, FIRST priority should be BRIGHTNESS before other adjustments
    - **MANDATORY FOR ALL PHOTOS FROM 1950-2000 ERA (especially 1970s-1980s)**: ALWAYS include these specific corrections in this priority order:
      1. BRIGHTNESS: increase by X% (IF UNDEREXPOSED - MANDATORY! typically 15-40% depending on darkness level)
      2. COLOR_TEMPERATURE: cool by XXXk (MANDATORY - to reduce warm/orange tint typical of old film)
      3. RED_CHANNEL: reduce by X% (MANDATORY - to desaturate reds/oranges - typically 12-18%)
      4. BLUE_CHANNEL: increase by X% (MANDATORY - to restore blue vibrancy and balance warm tint - typically 15-20%)
      5. GREEN_CHANNEL: increase by X% (MANDATORY - to brighten underexposed greens - typically 10-15%)
      6. VIBRANCE or SATURATION: increase by X% (to bring colors back to life - typically 15-25%)
    - **CRITICAL**: NOISE_REDUCTION MUST have a numeric strength value (e.g., "apply 20%", "apply 35%") - NEVER use words like "light", "moderate", "heavy" without a percentage
    - Examples of CORRECT format: 
      * "BRIGHTNESS: increase by 25%"
      * "CONTRAST: boost by 20%"
      * "SATURATION: increase by 15%"
      * "COLOR_TEMPERATURE: warm by 500K" (or "COLOR_TEMPERATURE: cool by 800K" for removing orange)
      * "SHARPNESS: increase by 30%"
      * "NOISE_REDUCTION: apply 25%" (MUST be numeric percentage)
      * "RED_CHANNEL: reduce by 15%" (for orange/yellow cast - ALWAYS INCLUDE for old photos)
      * "BLUE_CHANNEL: increase by 20%" (to restore blue balance - ALWAYS INCLUDE for warm casts!)
      * "GREEN_CHANNEL: increase by 15%" (to brighten underexposed greens - ALWAYS INCLUDE!)
      * "GREEN_SATURATION: increase by 20%" (to restore green vibrancy)
      * "UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0"
      * "SHADOWS: brighten by 15%"
      * "HIGHLIGHTS: reduce by 10%"
      * "VIBRANCE: increase by 20%"
      * "CLARITY: boost by 20%"
      * "YELLOW_CAST_REMOVAL: shift to neutral" (alternative for extreme cases)
    - DO NOT use phrases like "maintain", "normalize", "none needed", "as is"
    - DO NOT forget the percentage, value, or parameter for each action - EVERY recommendation must have a numeric value
    - List in order of priority/impact (COLOR_TEMPERATURE + RED_CHANNEL + BLUE_CHANNEL + GREEN_CHANNEL should ALWAYS be top 4 for warm/orange casts)
    - ALWAYS include at least 4-6 specific enhancement recommendations
    - **REMINDER: For images that look like they're from 1950-2000, ALWAYS recommend COLOR_TEMPERATURE cool shift + RED_CHANNEL reduce + BLUE_CHANNEL increase + GREEN_CHANNEL increase. This is NOT optional.**
    - ALWAYS include at least 3-5 specific enhancement recommendations (even if small)
    - **REMINDER: For images that look like they're from 1950-2000, ALWAYS recommend COLOR_TEMPERATURE cool shift + RED_CHANNEL reduce + BLUE_CHANNEL increase. This is NOT optional.**

18. **Overall Enhancement Priority**:
    - Which issue is most critical to fix first
    - Estimated improvement percentage if all recommendations applied
    - Preservation notes: aspects that should NOT be changed to maintain character

=== SLIDE RESTORATION PROFILES (MANDATORY - ALWAYS ANALYZE) ===
19. **Suggested Profiles** (MANDATORY FOR EVERY IMAGE): Analyze if this appears to be a scanned slide, dia positive, or vintage photograph, and suggest the most suitable restoration profiles with confidence scores (0-100%).
    Available profiles: 
    - faded: Very faded slides with lost color/contrast and washed-out appearance
    - color_cast: Generic color casts (any unusual color tint not covered by other profiles)
    - red_cast: Red/magenta aging (typical of old Kodachrome slides, reddish tint)
    - yellow_cast: Yellow/warm aging (golden/sepia tone, typical of older films)
    - aged: Moderate aging with slight color cast and contrast loss
    - well_preserved: Minimal aging, good color and contrast retention
    
    Format: ALWAYS return an array with 2-3 suggestions, ALWAYS INCLUDING well_preserved as baseline: [{{"profile": "detected_profile", "confidence": 75}}, {{"profile": "well_preserved", "confidence": 60}}]
    Examples:
    - For a faded slide: [{{"profile": "faded", "confidence": 85}}, {{"profile": "well_preserved", "confidence": 50}}]
    - For a red-cast slide: [{{"profile": "red_cast", "confidence": 80}}, {{"profile": "aged", "confidence": 60}}, {{"profile": "well_preserved", "confidence": 40}}]
    - For a yellow/orange vintage photo (1970s-80s film): [{{"profile": "yellow_cast", "confidence": 85}}, {{"profile": "color_cast", "confidence": 65}}, {{"profile": "well_preserved", "confidence": 35}}]
    - For a well-preserved slide: [{{"profile": "well_preserved", "confidence": 90}}, {{"profile": "aged", "confidence": 45}}]
    
    CRITICAL DETECTION RULES:
    1. If filename contains "dia", "slide", "transparency", "positive" → DEFINITELY analyze as slide/dia and provide profiles
    2. If image appears to be from before 2000 (especially 1970s-1980s) → expect strong color casts (orange/yellow/red typical of old film)
       - **ALSO APPLY**: When 1970s-80s photo is detected, ALWAYS recommend COLOR_TEMPERATURE cool + RED_CHANNEL reduce + BLUE_CHANNEL increase in enhancements (see section 17)
    3. If image has strong orange/yellow tint → use yellow_cast profile (high priority for 1970s-80s photos)
    4. If image has red/magenta tint → use red_cast profile
    5. If image has any color cast, fading, grain, or dust → do NOT return empty, match closest profile
    6. ALWAYS provide at least 2-3 profile recommendations including well_preserved as baseline
    7. well_preserved should ALWAYS be included (even if confidence is lower) as it's a safe baseline option
    8. If uncertain, default to "aged" or "well_preserved" with appropriate confidence (never return empty array for real photographs)
    
    IMPORTANT: Even scanned slides with minimal issues should get "well_preserved" profile. NEVER return [] for actual photographs.

Format your response as a structured JSON object with FOUR mandatory top-level keys:
- "metadata": {{"objects": "...", "persons": "...", "weather": "...", "mood_atmosphere": "...", "time_of_day": "...", "season_date": "...", "scene_type": "...", "location_setting": "...", "activity_action": "...", "photography_style": "...", "composition_quality": "..."}}
- "location_detection": {{"country": "...", "region": "...", "city_or_area": "...", "location_type": "...", "confidence": 0-100, "reasoning": "..."}}
- "enhancement": {{"lighting_quality": "...", "color_analysis": "...", "sharpness_clarity": "...", "contrast_level": "...", "composition_issues": "...", "recommended_enhancements": [...], "overall_priority": "..."}}
- "slide_profiles": [{{"profile": "profile_name", "confidence": 0-100}}, ...] - ALWAYS include this, even if empty []

CRITICAL REMINDER: You MUST respond in {language} for METADATA fields. Location detection MUST be in ENGLISH JSON format. This is essential for image metadata.
"""
