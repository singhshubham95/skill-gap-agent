"""Regenerate board/BOARD.md from board/locks/ (the human-readable view).

Usage: python scripts/board.py
"""
import sys

from locks_common import regenerate_board

if __name__ == "__main__":
    regenerate_board()
    print("board/BOARD.md regenerated")
    sys.exit(0)
