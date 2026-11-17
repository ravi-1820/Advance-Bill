from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from billing.serializers import (
    DistributorRegistrationSerializer,
    UserRegistrationSerializer,
    UserResponseSerializer
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
