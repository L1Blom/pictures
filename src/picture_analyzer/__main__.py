"""Entry point for ``python -m picture_analyzer``.

Delegates to the Click-based CLI in ``picture_analyzer.cli.app``.

.. note::

   When running from the project directory, the root-level
   ``picture_analyzer.py`` shim may shadow this package.  In that case
   ``python -m picture_analyzer`` will execute the shim, not this file.
   Use ``picture-analyzer`` (the installed console script) instead.
"""
from picture_analyzer.cli.app import main


if __name__ == "__main__":
    main()
