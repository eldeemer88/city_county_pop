"""Rebuild everything: sources -> panel -> graphs -> averages -> database -> single-file web app.

    python run_all.py            # full pipeline
    python app/serve.py          # then browse/search the results locally
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import build_db  # noqa: E402
import build_panel  # noqa: E402
import export_static  # noqa: E402
import fetch_sources  # noqa: E402
import make_aggregates  # noqa: E402
import make_graphs  # noqa: E402

if __name__ == "__main__":
    fetch_sources.fetch()
    build_panel.build()
    make_graphs.main(log=False)
    make_graphs.main(log=True)
    make_aggregates.main()
    build_db.build()
    export_static.main()
    print("\nDone. Open docs/index.html in a browser (no server needed), or run:  python app/serve.py")
