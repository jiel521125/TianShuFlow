"""User-scoped model configuration storage.

Each user can register their own LLM provider credentials and model
identifiers. These rows are kept in the shared SQL database so the
model list merges with the system-configured models at runtime.

The factory (``tianshu.models.factory``) consults the
``UserModelStore`` first when resolving ``model_name``, falling back
to the system ``AppConfig.models`` only if no user row matches.

This package mirrors the structure of ``persistence.agents`` so the
reader can compare the two side-by-side: a sync ``sql.py`` is
sufficient because the model factory is itself sync (same rationale
as documented in :mod:`tianshu.persistence.agents`).
"""

from __future__ import annotations