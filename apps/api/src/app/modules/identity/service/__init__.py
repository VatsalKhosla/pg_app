"""Use cases of the identity module; each method is one transaction."""

from app.modules.identity.service.consent import (
    ConsentGiven,
    ConsentService,
    PrivacyNotice,
    privacy_notice,
)
from app.modules.identity.service.export import personal_data
from app.modules.identity.service.otp import (
    OTP_RETENTION,
    IssuedChallenge,
    OtpService,
    SignedIn,
    delete_old_challenges,
)
from app.modules.identity.service.sessions import (
    SESSION_RETENTION,
    Authentication,
    IssuedSession,
    Person,
    Profile,
    SessionService,
    UserService,
    delete_finished_sessions,
    hash_token,
)
from app.modules.identity.service.staff import (
    Enrolment,
    GoogleLogin,
    StaffAdmin,
    StaffAdminError,
    StaffDirectory,
    StaffSignInService,
)

__all__ = [
    "OTP_RETENTION",
    "SESSION_RETENTION",
    "Authentication",
    "ConsentGiven",
    "ConsentService",
    "Enrolment",
    "GoogleLogin",
    "IssuedChallenge",
    "IssuedSession",
    "OtpService",
    "Person",
    "PrivacyNotice",
    "Profile",
    "SessionService",
    "SignedIn",
    "StaffAdmin",
    "StaffAdminError",
    "StaffDirectory",
    "StaffSignInService",
    "UserService",
    "delete_finished_sessions",
    "delete_old_challenges",
    "hash_token",
    "personal_data",
    "privacy_notice",
]
