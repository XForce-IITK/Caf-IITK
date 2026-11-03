"""Unknown query parameters are rejected like unknown body fields (NFR-22).

Request bodies forbid extra fields in their schemas; FastAPI silently ignores a
query parameter the endpoint does not declare, so `?limt=5` would quietly fall
back to the default limit. This app-wide dependency turns it into the same
field-level 422 an unknown body field gets.
"""

from fastapi import Request
from fastapi.dependencies.models import Dependant
from fastapi.exceptions import RequestValidationError

# By id(route): routes are not hashable. The route is kept with its names, so an
# id reused by a later route (tests build many apps) is not mistaken for it.
_declared: dict[int, tuple[object, frozenset[str]]] = {}


def _query_names(dependant: Dependant) -> set[str]:
    names = {param.alias for param in dependant.query_params}
    for sub in dependant.dependencies:
        names |= _query_names(sub)
    return names


def reject_unknown_query_params(request: Request) -> None:
    route = request.scope.get("route")
    dependant = getattr(route, "dependant", None)
    if route is None or dependant is None:
        return
    cached = _declared.get(id(route))
    if cached is None or cached[0] is not route:
        cached = _declared[id(route)] = (route, frozenset(_query_names(dependant)))
    declared = cached[1]
    unknown = [name for name in request.query_params if name not in declared]
    if unknown:
        raise RequestValidationError(
            [
                {
                    "type": "extra_forbidden",
                    "loc": ("query", name),
                    "msg": "Extra inputs are not permitted",
                }
                for name in dict.fromkeys(unknown)
            ]
        )
