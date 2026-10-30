"""Language adapter registry and factory."""

from typing import Dict, Optional

from patchpilot.languages.base import LanguageAdapter
from patchpilot.languages.java_adapter import JavaAdapter
from patchpilot.languages.js_adapter import JavaScriptAdapter, TypeScriptAdapter
from patchpilot.languages.python_adapter import PythonAdapter
from patchpilot.schemas.enums import Language


class LanguageAdapterRegistry:
    """Registry mapping languages to their concrete LanguageAdapter implementation."""

    _adapters: Dict[Language, LanguageAdapter] = {
        Language.PYTHON: PythonAdapter(),
        Language.JAVASCRIPT: JavaScriptAdapter(),
        Language.TYPESCRIPT: TypeScriptAdapter(),
        Language.JAVA: JavaAdapter(),
    }

    @classmethod
    def get_adapter(cls, language: Language) -> Optional[LanguageAdapter]:
        return cls._adapters.get(language)


registry = LanguageAdapterRegistry()
