import os
import sys

os.environ.setdefault("TESTING", "true")
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend")))
