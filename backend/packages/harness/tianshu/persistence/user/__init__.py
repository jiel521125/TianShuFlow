"""User storage subpackage.

Holds the ORM model for the ``users`` table. The concrete repository
implementation (``PostgresUserRepository``) lives in the app layer
(``app.gateway.auth.repositories.postgres``) because it converts
between the ORM row and the auth module's pydantic ``User`` class.
This keeps the harness package free of any dependency on app code.
"""

from tianshu.persistence.user.model import UserRow

__all__ = ["UserRow"]
