#!/usr/bin/env python
"""
test_fixed_ranking.py - helper script for manual validation of intermediate
ranking results.

This file is not meant to be executed automatically by the test suite, so we
explicitly mark it as non-test for pytest.
"""

__test__ = False  # prevents pytest from collecting this script as a test

import pytest
pytest.skip("helper script, not part of automated tests", allow_module_level=True)

import sys
from pathlib import Path

# Add the scripts directory to Python path so we can import modules
scripts_dir = Path(__file__).parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from compare_versions_refactored import rank_all_chapters

def main():
    """Test the fixed ranking system with validation."""
    
    print("🧪 Testing fixed intermediate results system...")
    
    # Test with a small subset to avoid long runtime
    output_path = Path("test_fixed.html")
    
    try:
        rank_all_chapters(
            output_path=output_path,
            max_versions=3,  # Limit to 3 versions per chapter for faster testing
            ranking_method="simple",  # Use simple method for faster execution
            save_intermediate=True,
        )
        
        print(f"✅ Test completed successfully!")
        print(f"📄 HTML report: {output_path}")
        
        # Check for intermediate results
        intermediate_dir = output_path.parent / "intermediate_results"
        if intermediate_dir.exists():
            intermediate_files = list(intermediate_dir.glob("rankings_*.json"))
            if intermediate_files:
                latest_file = max(intermediate_files, key=lambda p: p.stat().st_mtime)
                print(f"📊 Intermediate results: {latest_file}")
            else:
                print("⚠️  No intermediate files found")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 