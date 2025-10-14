"""PyInstaller runtime hook to silence pkg_resources deprecation warning.

PyInstaller 6.10 (and later) ships with a setuptools version that emits a
`UserWarning` once `pkg_resources` initializes. The packaged backend still
transitively imports `pkg_resources` (via FastAPI/Pydantic), so the warning
surfaces during bootstrap of the frozen binary. Filtering it here keeps the
console output clean while we gradually migrate away from the dependency.
"""

import warnings


warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
)
