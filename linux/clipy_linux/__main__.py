import sys

# Answer --version without importing GTK, so installers and scripts can check
# the installed version even when the GTK bindings are missing.
if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-v"):
    from . import APP_NAME, __version__
    print(f"{APP_NAME} for Linux {__version__}")
    sys.exit(0)

from .app import main  # noqa: E402

sys.exit(main())
