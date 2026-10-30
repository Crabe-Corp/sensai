import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

ALLOWED_DIR = Path("kingdom_manuscript").resolve()
ALLOWED_DIR.mkdir(exist_ok=True)
(ALLOWED_DIR / "brouillons").mkdir(exist_ok=True)

_confirmation_handler: ContextVar[Callable[[str], bool] | None] = ContextVar("confirmation_handler", default=None)

@contextmanager
def confirmation_handler(handler: Callable[[str], bool]) -> Iterator[None]:
    """Remplace temporairement l'invite console par un handler de confirmation.
            PARAMS: - handler - CALLABLE: reçoit le résumé de l'action, renvoie True si approuvée
            RETURN: gestionnaire de contexte"""

    token = _confirmation_handler.set(handler)
    try:
        yield
    finally:
        _confirmation_handler.reset(token)
