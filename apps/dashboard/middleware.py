class WorkspaceAdminFrameMiddleware:
    """Allow the same-origin workspace to frame Unfold management screens."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/admin/") and request.user.is_authenticated and request.user.is_staff:
            response["X-Frame-Options"] = "SAMEORIGIN"
        return response
