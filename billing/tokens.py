"""
Token utilities for secure, short-lived recovery authorization.
Prepared for Task 4 backend password reset boundary and Task 5 OTP email verification.
"""
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired


class AdminRecoveryTokenGenerator:
    """
    Cryptographically secure, short-lived, single-use token generator
    for Admin password recovery authorization.
    """
    SALT = 'billing.tokens.admin_password_recovery'
    MAX_AGE_SECONDS = 900  # 15 minutes

    @classmethod
    def generate_token(cls, user) -> str:
        """
        Generate a signed token encoding user.id, normalized email,
        and current password signature slice.
        """
        signer = TimestampSigner(salt=cls.SALT)
        # Using a slice of user.password ensures that once the password changes,
        # the token becomes immediately invalid (single-use guarantee).
        pwd_fingerprint = (user.password or '')[:24]
        payload = f"{user.id}:{user.email.strip().lower()}:{pwd_fingerprint}"
        return signer.sign(payload)

    @classmethod
    def verify_token(cls, token: str, user) -> tuple[bool, str | None]:
        """
        Verify the validity, freshness, and account binding of the recovery token.
        Returns (is_valid, error_message).
        """
        if not token:
            return False, "Password reset requires a valid recovery authorization mechanism."

        if not user:
            return False, "User account is required for token verification."

        signer = TimestampSigner(salt=cls.SALT)
        try:
            unsigned = signer.unsign(token, max_age=cls.MAX_AGE_SECONDS)
        except SignatureExpired:
            return False, "Recovery authorization token has expired."
        except BadSignature:
            return False, "Invalid recovery authorization token."

        parts = unsigned.split(":")
        if len(parts) != 3:
            return False, "Invalid recovery authorization token format."

        uid_str, email_str, pwd_slice = parts

        if str(user.id) != uid_str or user.email.strip().lower() != email_str.lower():
            return False, "Recovery token does not match the specified user account."

        expected_pwd_fingerprint = (user.password or '')[:24]
        if expected_pwd_fingerprint != pwd_slice:
            return False, "Recovery authorization has already been used or invalidated."

        return True, None


admin_recovery_token_generator = AdminRecoveryTokenGenerator()
