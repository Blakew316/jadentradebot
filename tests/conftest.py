import sys
from pathlib import Path

# Make the repo root importable when running `pytest` from a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
