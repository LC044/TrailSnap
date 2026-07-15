import sys
from pathlib import Path

# Add trailsnap directory to path so it can be imported without installation
sys.path.insert(0, str(Path(__file__).parent.parent))
