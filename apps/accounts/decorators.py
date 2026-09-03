from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required


def roles_required(*roles):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.primary_role not in roles and not request.user.is_superuser:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
