import random
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from billing.models import User


class UserResponseSerializer(serializers.ModelSerializer):
    """
    Safe read-only serializer for returning user data without sensitive credentials.
    """
    class Meta:
        model = User
        fields = [
            'id', 'name', 'email', 'phone', 'distributor_id',
            'company_name', 'usertype', 'today_sales', 'available_inventory'
        ]
        read_only_fields = fields


class DistributorRegistrationSerializer(serializers.Serializer):
    """
    Serializer specifically for public Distributor customer registration.
    Validates required fields, email format and uniqueness, phone formatting
    and uniqueness, company name, password match and Django password strength,
    and securely enforces usertype='distributor' on the server side.
    """
    name = serializers.CharField(max_length=100, required=True, allow_blank=False)
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        trim_whitespace=False
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        trim_whitespace=False
    )
    phone = serializers.CharField(max_length=20, required=True, allow_blank=False)
    company_name = serializers.CharField(max_length=150, required=True, allow_blank=False)
    usertype = serializers.CharField(required=False, default='distributor')

    def validate_email(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("An account with this email address already exists.")
        return normalized

    def validate_name(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Please enter your full name.")
        return stripped

    def validate_phone(self, value):
        stripped = value.strip()
        clean_digits = ''.join(c for c in stripped if c.isdigit())
        if len(clean_digits) < 10:
            raise serializers.ValidationError("Please enter a valid phone number (at least 10 digits).")
        if User.objects.filter(phone=stripped).exists():
            raise serializers.ValidationError("An account with this phone number already exists.")
        return stripped

    def validate_company_name(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Please enter your company / outlet name.")
        return stripped

    def validate_usertype(self, value):
        # Prevent privilege escalation: arbitrary frontend values are safely sanitized to distributor
        return 'distributor'

    def validate(self, attrs):
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')

        if password != password_confirm:
            raise serializers.ValidationError({
                'password_confirm': "Password confirmation does not match password."
            })

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({
                'password': list(exc.messages)
            })

        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm', None)
        raw_password = validated_data.pop('password')
        # Server-side enforcement of distributor role
        validated_data['usertype'] = 'distributor'

        user = User.objects.create_user(
            password=raw_password,
            **validated_data
        )
        return user


class UserRegistrationSerializer(serializers.Serializer):
    """
    Serializer for admin-initiated user registration.
    Validates email format, email uniqueness, password confirmation,
    Django password validators, and creates accounts using secure hashing.
    """
    name = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        trim_whitespace=False
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        trim_whitespace=False
    )
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
    company_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    distributor_id = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    usertype = serializers.ChoiceField(choices=['distributor', 'admin'], default='distributor', required=False)

    def validate_email(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("An account with this email address already exists.")
        return normalized

    def validate_phone(self, value):
        stripped = value.strip()
        if stripped:
            clean_digits = ''.join(c for c in stripped if c.isdigit())
            if len(clean_digits) < 10:
                raise serializers.ValidationError("Phone number must contain at least 10 digits.")
            if User.objects.filter(phone=stripped).exists():
                raise serializers.ValidationError("An account with this phone number already exists.")
        return stripped

    def validate(self, attrs):
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')

        if password != password_confirm:
            raise serializers.ValidationError({
                'password_confirm': "Password confirmation does not match password."
            })

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({
                'password': list(exc.messages)
            })

        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm', None)
        raw_password = validated_data.pop('password')
        usertype = validated_data.get('usertype', 'distributor')

        distributor_id = validated_data.get('distributor_id', '').strip()
        if usertype == 'distributor' and not distributor_id:
            while True:
                candidate_id = f"DIST-{random.randint(10000, 99999)}"
                if not User.objects.filter(distributor_id=candidate_id).exists():
                    distributor_id = candidate_id
                    break
            validated_data['distributor_id'] = distributor_id

        user = User.objects.create_user(
            password=raw_password,
            **validated_data
        )
        return user
