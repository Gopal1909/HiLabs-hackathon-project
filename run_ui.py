"""
run_ui.py
Interactive Executive & Analyst Web Dashboard Launcher.
HiLabs AI Quest Hackathon Deliverable 7(a) (Brownie Points).

Usage:
  python run_ui.py                 # Launches dashboard server and opens browser
  python run_ui.py --export-only   # Regenerates static HTML without starting server
  python run_ui.py --port 8080     # Custom port
"""
import sys
from src.ui import main

if __name__ == "__main__":
    main()
