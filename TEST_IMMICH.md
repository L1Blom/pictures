# Testing Metadata & GPS in Immich

## What's Now Embedded in Your Images

### 1. **Comprehensive Metadata (in User's Language)**
All analysis results stored in two places:

- **ImageDescription Field** (visible in Immich):
  - **LOCATION**: Auto-detected geographic location (e.g., "Duitsland, Berlijn, Treptower Park")
  - **Confidence**: Location detection confidence (0-100%)
  - **Objects**, **Persons**, **Weather**, **Mood/Atmosphere**, **Time of Day**
  - **Season/Date**, **Scene Type**, **Setting**, **Activity**
  - **Photography Style**, **Composition Quality**
  - ✨ All metadata text generated in your configured language (Dutch, English, etc.)

- **UserComment Field** (JSON backup):
  - Complete structured data: metadata, enhancement, location_detection
  - Durable storage even if EXIF fields are stripped
  - All 11 metadata fields + location + enhancement recommendations

### 2. **GPS Coordinates (Auto-Generated from Location Detection)**
When location confidence ≥ 80%:

- **GPS IFD** (EXIF standard GPS fields):
  - Latitude and Longitude (DMS format)
  - GPSVersionID and GPSMapDatum (WGS-84)
  - ✨ Compatible with Immich map display
  - Works with any photo tool that reads standard GPS EXIF

## How to Test in Immich

### Step 1: Verify Metadata is Present
```bash
python3 verify_image_metadata.py output/image_analyzed.jpg
```

Shows:
- ✓ All metadata fields and their values
- ✓ Location detection data
- ✓ GPS coordinates (if generated)
- ✓ Timestamps and data structure

### Step 2: Upload to Immich
1. Copy analyzed images to your Immich library:
```bash
cp output/*_analyzed.jpg /path/to/immich/library/
```

2. Refresh Immich's library (Settings → Library → Rescan)

### Step 3: What to See in Immich

**In Image Information Panel:**
- **Description/Info tab**: Shows ImageDescription (all metadata + location)
  - `LOCATIE: Duitsland, Berlijn, Treptower Park (Betrouwbaarheid: 95%)`
  - All metadata fields formatted nicely
  
- **Map view** (if GPS embedded):
  - Click map icon to see exact coordinates
  - Coordinates derived from location detection with 95%+ accuracy
  - Only embedded when confidence ≥ 80%

**Raw EXIF Display:**
```bash
exiftool output/*_analyzed.jpg | grep -i "gps\|description\|location"
```

Should show:
```
GPS Version ID                  : 2.2.0.0
GPS Latitude                    : 52 deg 31' 12.00"
GPS Longitude                   : 13 deg 24' 10.76"
GPS Latitude Ref                : North
GPS Longitude Ref               : East
GPS Map Datum                   : WGS-84
Image Description               : LOCATIE: Duitsland, Berlijn, Treptower Park...
```

## Language Configuration

Metadata appears in your configured language:

```bash
# Set to Dutch
export METADATA_LANGUAGE=nl
python3 cli.py process image.jpg

# Set to English
export METADATA_LANGUAGE=en
python3 cli.py process image.jpg
```

Or in `.env`:
```
METADATA_LANGUAGE=nl
GPS_CONFIDENCE_THRESHOLD=80
```

## GPS Configuration

Control when GPS coordinates are embedded:

```bash
# Default: embed GPS when confidence ≥ 80%
export GPS_CONFIDENCE_THRESHOLD=80

# More conservative: only embed when 90%+ confident
export GPS_CONFIDENCE_THRESHOLD=90

# Aggressive: embed whenever location detected (≥ 50%)
export GPS_CONFIDENCE_THRESHOLD=50
```

## Troubleshooting

### Metadata Not Showing in Immich
1. Check with verification script:
   ```bash
   python3 verify_image_metadata.py image.jpg
   ```

2. Verify EXIF with exiftool:
   ```bash
   exiftool image.jpg | head -30
   ```

3. Force Immich rescan:
   - Settings → Library → Rescan
   - Delete and re-add the image

### GPS Not Showing
- Check confidence threshold: `echo $GPS_CONFIDENCE_THRESHOLD`
- Verify geocoding worked: Check for gps_coordinates in JSON output
- Try lower confidence threshold for testing
- Location must be real and geocodable (Nominatim lookup)

### Performance Issues
GPS coordinates are cached locally to avoid repeated API calls:
- Cache file: `.geocoding_cache.json`
- Clear cache if needed: `rm .geocoding_cache.json`
- First run of unique locations will call Nominatim API (minimal delay)

## Sample Output

For Berlin image with clear landmarks:
```
LOCATIE: Duitsland, Berlijn, Brandenburger Tor (Betrouwbaarheid: 95%)

Objecten: Historisch monument met imposante architectuur...
Personen: Geen personen zichtbaar
Weer: Heldere dag
Sfeer/Atmosfeer: Majestueus, historisch
Tijd van de dag: Middag
Seizoen/Datum: Herfst, omstreeks oktober
Type scène: Architectuurfotografie, monumentenfotografie
Omgeving: Buiten, stedelijk centrum
Activiteit: Toeristische fotografie
Fotografische stijl: Documentaire, architecturale fotografie
Samenstelling kwaliteit: Excellent

GPS: 52.5161°N, 13.3819°E (Brandenburger Tor, Berlin)
```
