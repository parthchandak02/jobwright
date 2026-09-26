"""Enable `python -m jobwright` (records the exit code of dashboard-spawned runs)."""

import os

from jobwright.cli import app


def _main() -> None:
    run_id = os.environ.get("JOBWRIGHT_WEB_RUN_ID", "").strip()
    code = 0
    try:
        app()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        raise
    except BaseException:
        code = 1
        raise
    finally:
        if run_id:
            try:
                from jobwright.run_registry import finish_run

                finish_run(run_id, code)
            except Exception:  # noqa: BLE001 - never mask the real exit
                pass


if __name__ == "__main__":
    _main()
