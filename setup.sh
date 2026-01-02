#!/bin/bash
# Quick start guide for Picture Analysis Project

echo "=========================================="
echo "Picture Analysis Project - Quick Start"
echo "=========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "1. Creating Python virtual environment..."
    python3 -m venv venv
    echo "   ✓ Virtual environment created"
else
    echo "1. Virtual environment already exists"
fi

echo ""
echo "2. Activating virtual environment..."
source venv/bin/activate
echo "   ✓ Virtual environment activated"

echo ""
echo "3. Installing dependencies..."
pip install -q -r requirements.txt
echo "   ✓ Dependencies installed"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "To analyze a single image:"
echo "  python cli.py analyze path/to/image.jpg"
echo ""
echo "To analyze multiple images in a directory:"
echo "  python cli.py batch path/to/pictures/"
echo ""
echo "To use in Python code:"
echo "  from picture_analyzer import PictureAnalyzer"
echo "  analyzer = PictureAnalyzer()"
echo "  results = analyzer.analyze_and_save('image.jpg')"
echo ""
echo "Virtual environment is active. To deactivate, run: deactivate"
echo ""
