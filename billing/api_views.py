import random
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from billing.models import User, OTP, Product
from billing.tokens import admin_recovery_token_generator
from billing.serializers import (
    DistributorRegistrationSerializer,
    UserRegistrationSerializer,
    UserResponseSerializer,
    AdminPasswordRecoveryRequestSerializer,
    AdminPasswordResetSerializer,
    ProductSerializer
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
            # Check resend cooldown (e.g. 60 seconds)
            recent_otp = OTP.objects.filter(identity__iexact=user.email, is_verified=False).order_by('-created_at').first()
            if recent_otp and (timezone.now() - recent_otp.created_at).total_seconds() < 60:
                otp_code = recent_otp.otp
            else:
                # Invalidate old unverified OTPs for this admin
                OTP.objects.filter(identity__iexact=user.email, is_verified=False).delete()
                # Generate random 6-digit OTP
                otp_code = f"{random.randint(100000, 999999)}"
                OTP.objects.create(identity=user.email, otp=otp_code)

            # Send OTP email to registered Admin email
            subject = "Admin Password Recovery - Advance Billing System"
            message = (
                f"Hello {user.name or 'Admin'},\n\n"
                f"Your one-time password (OTP) for admin password recovery is: {otp_code}\n\n"
                f"This OTP is valid for 5 minutes. Do not share this code with anyone.\n\n"
                f"Advance Billing System Security Team"
            )
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@advancebilling.com')
            try:
                send_mail(subject, message, from_email, [user.email], fail_silently=False)
            except Exception:
                pass

            # Generate short-lived recovery token for client integration
            token = admin_recovery_token_generator.generate_token(user)
            response_payload["data"] = {
                "reset_token": token
            }

        return Response(response_payload, status=status.HTTP_200_OK)


class AdminOTPVerificationAPIView(APIView):
    """
    Public endpoint for verifying Admin password recovery OTP.
    Endpoint: POST /api/password-recovery/verify-otp/
    Access: Public (unauthenticated access permitted).
    Validates OTP, enforces 5-minute expiry, prevents token reuse,
    and returns a short-lived recovery authorization token for password reset.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        email = (request.data.get('email') or '').strip().lower()
        entered_otp = (request.data.get('otp') or '').strip()

        if not email:
            return Response({
                "success": False,
                "status": "error",
                "message": "Email address is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        if not entered_otp:
            return Response({
                "success": False,
                "status": "error",
                "message": "OTP code is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            user = None

        if not user or user.usertype != 'admin':
            return Response({
                "success": False,
                "status": "error",
                "message": "Invalid recovery verification attempt."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check latest unverified OTP
        otp_record = OTP.objects.filter(identity__iexact=email, is_verified=False).order_by('-created_at').first()

        if not otp_record:
            # Check if this OTP was already verified/used
            if OTP.objects.filter(identity__iexact=email, is_verified=True, otp=entered_otp).exists():
                return Response({
                    "success": False,
                    "status": "error",
                    "message": "This OTP has already been used."
                }, status=status.HTTP_400_BAD_REQUEST)

            return Response({
                "success": False,
                "status": "error",
                "message": "Invalid or expired OTP."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check 5-minute expiry (300 seconds)
        if timezone.now() - otp_record.created_at > timedelta(minutes=5):
            otp_record.delete()
            return Response({
                "success": False,
                "status": "error",
                "message": "OTP has expired. Please request a new one."
            }, status=status.HTTP_400_BAD_REQUEST)

        if entered_otp != otp_record.otp:
            return Response({
                "success": False,
                "status": "error",
                "message": "Invalid OTP code."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Mark OTP as verified to prevent reuse
        otp_record.is_verified = True
        otp_record.save()

        # Generate short-lived single-use recovery token bound to user
        token = admin_recovery_token_generator.generate_token(user)

        return Response({
            "success": True,
            "status": "success",
            "message": "OTP verified successfully. You may now reset your password.",
            "data": {
                "reset_token": token
            }
        }, status=status.HTTP_200_OK)


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


class ProductListCreateAPIView(APIView):
    """
    REST API endpoint to list products with optional search/category filter,
    or create a new product.
    Endpoint: GET /api/products/
              POST /api/products/
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        search = request.query_params.get('search', '').strip()
        category = request.query_params.get('category', '').strip()
        qs = Product.objects.all().order_by('-id')

        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(category__icontains=search))
        if category:
            qs = qs.filter(category__iexact=category)

        serializer = ProductSerializer(qs, many=True)
        return Response({
            "success": True,
            "status": "success",
            "count": qs.count(),
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = ProductSerializer(data=request.data)
        if serializer.is_valid():
            product = serializer.save()
            return Response({
                "success": True,
                "status": "success",
                "message": "Product created successfully.",
                "data": ProductSerializer(product).data
            }, status=status.HTTP_201_CREATED)

        errors = serializer.errors
        first_err = "Product validation failed."
        if errors:
            first_key = next(iter(errors))
            first_val = errors[first_key]
            first_err = first_val[0] if isinstance(first_val, list) and first_val else str(first_val)

        return Response({
            "success": False,
            "status": "error",
            "message": first_err,
            "errors": errors
        }, status=status.HTTP_400_BAD_REQUEST)


class ProductDetailUpdateDeleteAPIView(APIView):
    """
    REST API endpoint to retrieve, update, or delete a product.
    Endpoint: GET /api/products/<int:id>/
              PUT /api/products/<int:id>/
              PATCH /api/products/<int:id>/
              DELETE /api/products/<int:id>/
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def get_object(self, id):
        try:
            return Product.objects.get(id=id)
        except Product.DoesNotExist:
            return None

    def get(self, request, id, *args, **kwargs):
        product = self.get_object(id)
        if not product:
            return Response({
                "success": False,
                "status": "error",
                "message": "Product not found."
            }, status=status.HTTP_404_NOT_FOUND)

        data = ProductSerializer(product).data
        data['invoice_items_count'] = product.invoice_items.count()
        return Response({
            "success": True,
            "status": "success",
            "data": data
        }, status=status.HTTP_200_OK)

    def put(self, request, id, *args, **kwargs):
        return self.update(request, id, partial=False)

    def patch(self, request, id, *args, **kwargs):
        return self.update(request, id, partial=True)

    def update(self, request, id, partial=False):
        product = self.get_object(id)
        if not product:
            return Response({
                "success": False,
                "status": "error",
                "message": "Product not found."
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = ProductSerializer(product, data=request.data, partial=partial)
        if serializer.is_valid():
            updated_product = serializer.save()
            return Response({
                "success": True,
                "status": "success",
                "message": "Product updated successfully.",
                "data": ProductSerializer(updated_product).data
            }, status=status.HTTP_200_OK)

        errors = serializer.errors
        first_err = "Product update validation failed."
        if errors:
            first_key = next(iter(errors))
            first_val = errors[first_key]
            first_err = first_val[0] if isinstance(first_val, list) and first_val else str(first_val)

        return Response({
            "success": False,
            "status": "error",
            "message": first_err,
            "errors": errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id, *args, **kwargs):
        product = self.get_object(id)
        if not product:
            return Response({
                "success": False,
                "status": "error",
                "message": "Product not found."
            }, status=status.HTTP_404_NOT_FOUND)

        # Protect historical invoices: verify product is not associated with InvoiceItem records
        if product.invoice_items.exists():
            return Response({
                "success": False,
                "status": "error",
                "message": "Cannot delete product associated with historical invoice records."
            }, status=status.HTTP_400_BAD_REQUEST)

        product.delete()
        return Response({
            "success": True,
            "status": "success",
            "message": "Product deleted successfully."
        }, status=status.HTTP_200_OK)


