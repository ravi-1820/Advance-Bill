import base64
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from billing.models import User


class AdminAuthentication(BaseAuthentication):
    """
    Custom DRF authentication class supporting:
    1. Active Django session with 'user_id'
    2. HTTP Basic Authentication header (email:password)
    """

    def authenticate(self, request):
        session = getattr(request, 'session', None)
        if session and session.get('user_id'):
            try:
                user = User.objects.get(id=session['user_id'])
                return (user, None)
            except User.DoesNotExist:
                pass

        auth_header = get_authorization_header(request).split()
        if auth_header and auth_header[0].lower() == b'basic' and len(auth_header) == 2:
            try:
                decoded = base64.b64decode(auth_header[1]).decode('utf-8')
                email, password = decoded.split(':', 1)
                user = User.objects.get(email=email)
                if user.check_password(password):
                    return (user, None)
            except (ValueError, UnicodeDecodeError, User.DoesNotExist):
                return None

        return None

    def authenticate_header(self, request):
        return 'Basic realm="api"'


class IsAdminUserRole(BasePermission):
    """
    Permission class allowing access ONLY to authenticated users with 'admin' usertype.
    - Unauthenticated requests: returns 401 Unauthorized (via NotAuthenticated).
    - Authenticated non-admin requests: returns 403 Forbidden (via PermissionDenied).
    """

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False) or not isinstance(user, User):
            raise NotAuthenticated('Authentication credentials were not provided.')

        if user.usertype != 'admin':
            raise PermissionDenied('You do not have permission to perform this action. Administrator access required.')

        return True
