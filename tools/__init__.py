from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "wiki"
PLUGIN = ROOT / "plugins" / "english-flow"
DOIST_CATALOG = PLUGIN / "doist-catalog.json"
sys.path.insert(0, str(PLUGIN))
