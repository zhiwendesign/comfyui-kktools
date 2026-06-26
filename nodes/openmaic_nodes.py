"""OpenMAIC standalone nodes bundled inside kktools.

This bridge lets kktools' node auto-discovery expose the OpenMAIC node classes
without changing their ComfyUI class type names.
"""

import importlib.util
import os
import sys


_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_OPENMAIC_DIR = os.path.join(_THIS_DIR, "openmaic")
_OPENMAIC_INIT = os.path.join(_OPENMAIC_DIR, "__init__.py")
_PACKAGE_NAME = "kktools_openmaic"

if not os.path.isfile(_OPENMAIC_INIT):
    raise ImportError(f"OpenMAIC bundle is missing: {_OPENMAIC_INIT}")

if _PACKAGE_NAME in sys.modules:
    _openmaic_module = sys.modules[_PACKAGE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(
        _PACKAGE_NAME,
        _OPENMAIC_INIT,
        submodule_search_locations=[_OPENMAIC_DIR],
    )
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Unable to load OpenMAIC bundle: {_OPENMAIC_INIT}")
    _openmaic_module = importlib.util.module_from_spec(_spec)
    sys.modules[_PACKAGE_NAME] = _openmaic_module
    _spec.loader.exec_module(_openmaic_module)

NODE_CLASS_MAPPINGS = dict(getattr(_openmaic_module, "NODE_CLASS_MAPPINGS", {}))
NODE_DISPLAY_NAME_MAPPINGS = dict(getattr(_openmaic_module, "NODE_DISPLAY_NAME_MAPPINGS", {}))

globals().update(NODE_CLASS_MAPPINGS)

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    *NODE_CLASS_MAPPINGS.keys(),
]
