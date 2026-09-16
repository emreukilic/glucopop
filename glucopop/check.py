"""Command-line connection check using the saved config:  python -m glucopop.check"""
import sys

from .config import Config
from .core import error_text
from . import sources


def main() -> int:
    try:
        import truststore; truststore.inject_into_ssl()
    except Exception:
        pass
    cfg = Config()
    if not cfg["source"]:
        print("No source configured yet. Run GlucoPop once and complete the setup wizard.")
        return 1
    print(f"source: {cfg['source']}  user: {cfg['source_cfg'].get('username') or cfg['source_cfg'].get('url')}")
    try:
        src = sources.create(cfg["source"], dict(cfg["source_cfg"]))
        src.connect()
        r = src.latest()
    except Exception as e:  # noqa: BLE001
        print("FAILED:", error_text(e))
        import traceback; traceback.print_exc()
        return 2
    print(f"OK: {r.value_text(cfg['unit'])} {cfg['unit']} {r.arrow}  age={r.age_seconds}s  person={r.person!r}  extra={r.extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
