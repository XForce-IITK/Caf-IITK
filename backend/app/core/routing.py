"""The route template a request matched, for metrics and access logs."""

from weakref import WeakKeyDictionary

from fastapi.routing import iter_route_contexts
from starlette.types import Scope

# A request that matched no route is labelled with this, not its path, so that
# probing random URLs cannot create an unbounded number of series or log values.
UNMATCHED_ROUTE = "<unmatched>"

_templates: WeakKeyDictionary[object, dict[int, str]] = WeakKeyDictionary()


def route_template(scope: Scope) -> str:
    """`/api/v1/orders/{order_id}`, not the path with the ID in it.

    The router stores the route as declared in its module router, without the
    /api/v1 prefix; the app's route contexts know the full path.
    """
    route = scope.get("route")
    if route is None:
        return UNMATCHED_ROUTE
    app = scope["app"]
    templates = _templates.get(app)
    if templates is None:
        templates = {
            id(context.original_route): context.path_format
            for context in iter_route_contexts(app.routes)
            if context.path_format
        }
        _templates[app] = templates
    return templates.get(id(route), getattr(route, "path", UNMATCHED_ROUTE))
