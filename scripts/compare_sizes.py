#!/usr/bin/env python
"""Compare line counts between original and refactored writer.py"""

with open('writer.py', 'r') as f:
    orig_lines = len(f.readlines())

with open('writer_refactored.py', 'r') as f:
    new_lines = len(f.readlines())

print(f"Original writer.py: {orig_lines} lines")
print(f"Refactored writer.py: {new_lines} lines")
print(f"Reduction: {orig_lines - new_lines} lines ({(orig_lines - new_lines) / orig_lines * 100:.1f}%)") 