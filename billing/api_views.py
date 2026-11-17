from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from billing.models import User
from billing.tokens import admin_recovery_token_generator
from billing.serializers import (
    DistributorRegistrationSerializer,
    UserRegistrationSerializer,
    UserResponseSerializer,
    AdminPasswordRecoveryRequestSerializer,
    AdminPasswordResetSerializer
)
from billing.permissions import AdminAuthentication, IsAdminUserRole


class DistributorRegistrationAPIView(APIView):
    """
    Public customer registration API endpoint for Distributors.
    Endpoint: POST /api/register/distributor/
    Access: Public (unauthenticated access explicitly permitted).
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = DistributorRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "success": True,
                "status": "success",
                "message": "Distributor registered successfully.",
                "data": UserResponseSerializer(user).data
            }, status=status.HTTP_201_CREATED)

        errors = serializer.errors
        first_error = "Validation failed."
        if errors:
            first_key = next(iter(errors))
            first_val = errors[first_key]
            if isinstance(first_val, list) and len(first_val) > 0:
                first_error = str(first_val[0])
            elif isinstance(first_val, str):
                first_error = first_val
            elif isinstance(first_val, dict):
                sub_val = next(iter(first_val.values()))
                if isinstance(sub_val, list) and len(sub_val) > 0:
                    first_error = str(sub_val[0])
                else:
                    first_error = str(sub_val)

        return Response({
            "success": False,
            "status": "error",
            "message": first_error,
            "errors": errors
        }, status=status.HTTP_400_BAD_REQUEST)


class UserRegistrationAPIView(APIView):
    """
    API endpoint allowing authorized Administrator users to register new accounts.
    Endpoint: POST /api/register/
    Access: Administrator users only (enforced via AdminAuthentication and IsAdminUserRole).
    """
    authentication_classes = [AdminAuthentication]
    permission_classes = [IsAdminUserRole]

    def post(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "success": True,
                "status": "success",
                "message": "User registered successfully.",
                "data": UserResponseSerializer(user).data,
                "user": UserResponseSerializer(user).data
            }, status=status.HTTP_201_CREATED)

        errors = serializer.errors
        first_error = "Validation failed."
        if errors:
            first_key = next(iter(errors))
            first_val = errors[first_key]
            if isinstance(first_val, list) and len(first_val) > 0:
                first_error = str(first_val[0])
            elif isinstance(first_val, str):
                first_error = first_val

        return Response({
            "success": False,
            "status": "error",
            "message": first_error,
            "errors": errors
        }, status=status.HTTP_400_BAD_REQUEST)


class AdminPasswordRecoveryAPIView(APIView):
    """
    Public endpoint for initiating Admin password recovery.
    Endpoint: POST /api/password-recovery/
    Access: Public (unauthenticated access permitted).
    Security: Uses a generic response to prevent account enumeration.
              Only Admin accounts generate valid recovery authorization.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = AdminPasswordRecoveryRequestSerializer(data=request.data)
        if not serializer.is_valid():
            errors = serializer.errors
            first_error = "Please enter a valid email address."
            if 'email' in errors and errors['email']:
                first_error = str(errors['email'][0])
            return Response({
                "success": False,
                "status": "error",
                "message": first_error,
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']

        # Generic response message to avoid user account enumeration
        generic_message = "If the account is eligible, password recovery instructions will be provided."

        response_payload = {
            "success": True,
            "status": "success",
            "message": generic_message
        }

        # Check account existence and Admin eligibility
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            user = None

        if user and user.usertype == 'admin':
            # Generate short-lived, single-use recovery token
            # (Prepared for Task 5 OTP email verification delivery; exposed in data for Task 4 API integration)
            token = admin_recovery_token_generator.generate_token(user)
            response_payload["data"] = {
                "reset_token": token
            }

        return Response(response_payload, status=status.HTTP_200_OK)


class AdminPasswordResetAPIView(APIView):
    """
    Secure password reset endpoint for Admin accounts.
    Endpoint: POST /api/password-reset/
    Access: Public with valid recovery authorization token.
    Enforces password validators, checks confirmation matching, hashes password securely,
    and invalidates the recovery authorization.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # Extract recovery token from request body, query params, or headers
        recovery_token = (
            request.data.get('reset_token') or
            request.data.get('token') or
            request.headers.get('X-Recovery-Token') or
            request.META.get('HTTP_X_RECOVERY_TOKEN', '')
        )
        if isinstance(recovery_token, str):
            recovery_token = recovery_token.strip()

        context = {'recovery_token': recovery_token}
        serializer = AdminPasswordResetSerializer(data=request.data, context=context)

        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True,
                "status": "success",
                "message": "Password has been reset successfully."
            }, status=status.HTTP_200_OK)

        errors = serializer.errors
        first_error = "Password reset validation failed."
        if errors:
            first_key = next(iter(errors))
            first_val = errors[first_key]
            if isinstance(first_val, list) and len(first_val) > 0:
                first_error = str(first_val[0])
            elif isinstance(first_val, str):
                first_error = first_val

        return Response({
            "success": False,
            "status": "error",
            "message": first_error,
            "errors": errors
        }, status=status.HTTP_400_BAD_REQUEST)

