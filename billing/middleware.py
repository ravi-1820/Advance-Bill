from django.contrib.auth.models import AnonymousUser
from billing.models import User


class SessionAuthenticationMiddleware:
    """
    Middleware ensuring request.user is consistently populated with the
    authenticated billing.models.User instance for both Django session auth
    and session user_id lookups.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # If request.user is missing or anonymous, resolve from session user_id
        if not getattr(request, 'user', None) or not request.user.is_authenticated:
            user_id = request.session.get('user_id')
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if getattr(user, 'is_active', True):
                        request.user = user
                    else:
                        request.user = AnonymousUser()
                except User.DoesNotExist:
                    request.user = AnonymousUser()
        elif getattr(request, 'user', None) and request.user.is_authenticated:
            # Check if active status changed during the session
            if not getattr(request.user, 'is_active', True):
                request.user = AnonymousUser()

        response = self.get_response(request)
        return response
