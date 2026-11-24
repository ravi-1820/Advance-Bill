from django.contrib.auth.backends import BaseBackend
from django.db.models import Q
from billing.models import User


class BillingModelBackend(BaseBackend):
    """
    Session-based Authentication Backend for Advance Billing System.
    Validates Admin and Distributor credentials, ensures active status,
    and returns billing.models.User for Django's session authentication.
    """

    def authenticate(self, request, username=None, password=None, usertype=None, **kwargs):
        if not password:
            return None

        identifier = (
            username or
            kwargs.get('email') or
            kwargs.get('identity') or
            kwargs.get('admin_email') or
            kwargs.get('distributor_id')
        )
        mobile = kwargs.get('mobile') or kwargs.get('phone')

        user = None

        # 1. Search by mobile number if provided
        if mobile:
            clean_mobile = ''.join(c for c in str(mobile) if c.isdigit())
            user = User.objects.filter(Q(phone=mobile) | Q(phone=clean_mobile)).first()

        # 2. Search by identifier (email, distributor_id, name, or phone)
        if not user and identifier:
            identifier_str = str(identifier).strip()
            user = User.objects.filter(
                Q(email__iexact=identifier_str) |
                Q(distributor_id__iexact=identifier_str) |
                Q(name__iexact=identifier_str) |
                Q(phone=identifier_str)
            ).first()

        # 3. Check password and account state
        if user and user.check_password(password):
            if not getattr(user, 'is_active', True):
                return None
            if usertype and user.usertype != usertype:
                return None
            return user

        return None

    def get_user(self, user_id):
        try:
            user = User.objects.get(pk=user_id)
            if not getattr(user, 'is_active', True):
                return None
            return user
        except (User.DoesNotExist, ValueError, TypeError):
            return None
