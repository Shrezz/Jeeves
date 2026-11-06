"""
errors.py
=========
Exceptions the parent module should catch and turn into user-facing messages.
"""


class PolicyRagError(Exception):
    """Base class for all errors raised by this package."""


class DocumentNotFoundError(PolicyRagError):
    """The file named in IngestRequest does not exist in config.UPLOAD_DIR."""


class PolicyMismatchError(PolicyRagError):
    """The policy number printed in the PDF does not match the one the parent passed.
    Prevents a user from attaching their identity to someone else's policy."""


class PolicyNotIngestedError(PolicyRagError):
    """A question was asked for a policy (and user) that has no stored chunks."""


class InvalidRequestError(PolicyRagError):
    """A required field (user_id, policy_number, question, file_name) is missing or blank."""
