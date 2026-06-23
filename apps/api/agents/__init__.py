"""
apps/api/agents — PanelMind agent configuration.

This package contains the persona catalog (YAML) and any future agent
configuration that's shared between the API and the web app.

Layout
──────
    personas/        one YAML per persona
    loader.py        reads YAMLs, returns a typed catalog
    catalog.py       runtime data classes (Persona, PersonaCatalog)
"""

__all__: list[str] = []
