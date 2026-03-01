#!/usr/bin/env python3
"""
Script to generate review audio files for both English and German
Run this script from the backend directory: python generate_review_audio.py
"""
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from services.azure_tts_service import get_azure_tts_service

def main():
    print("🎵 Generating review audio files...")
    
    tts_service = get_azure_tts_service()
    
    # Generate English files
    print("\n📝 Generating English review audio files...")
    result_en = tts_service.generate_review_prompts(language='en')
    if result_en.get("success"):
        print(f"✅ Generated {result_en.get('count', 0)} English files")
        for file in result_en.get("files", []):
            print(f"   - {file}")
    else:
        print(f"❌ Failed to generate English files: {result_en.get('error')}")
        return 1
    
    # Generate German files
    print("\n📝 Generating German review audio files...")
    result_de = tts_service.generate_review_prompts(language='de')
    if result_de.get("success"):
        print(f"✅ Generated {result_de.get('count', 0)} German files")
        for file in result_de.get("files", []):
            print(f"   - {file}")
    else:
        print(f"❌ Failed to generate German files: {result_de.get('error')}")
        return 1
    
    print("\n🎉 All review audio files generated successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())


