"""Collect SciPy special-function extensions that actually ship in SciPy."""

from importlib.util import find_spec

from PyInstaller.utils.hooks import is_module_satisfies

hiddenimports = ["scipy.special._ufuncs_cxx"]

if is_module_satisfies("scipy >= 1.14.0"):
    hiddenimports.append("scipy.special._special_ufuncs")

# PyInstaller Hooks-Contrib currently assumes _cdflib exists in every SciPy
# version >= 1.13, but some distributions (including the pinned 1.18.1 build)
# omit this optional extension. Keep it only when it is present.
try:
    cdflib_spec = find_spec("scipy.special._cdflib")
except (ImportError, ModuleNotFoundError, ValueError):
    cdflib_spec = None

if cdflib_spec is not None:
    hiddenimports.append("scipy.special._cdflib")
