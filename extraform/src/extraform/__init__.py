"""ExtraForm: Pull, edit, and push Google Forms using local files."""

from extraform.client import FormsClient, PullResult, PushResult
from extraform.diff import DiffResult, ItemChange, diff_forms
from extraform.exceptions import (
    AuthenticationError,
    DiffError,
    ExtraFormError,
    InvalidFileError,
    MissingPristineError,
    NotFoundError,
    TransportError,
)
from extraform.file_reader import read_current_files
from extraform.pristine import extract_pristine
from extraform.request_generator import generate_requests
from extraform.transformer import FormTransformer
from extraform.transport import (
    FormTransport,
    GoogleFormsTransport,
    LocalFileTransport,
)
from extraform.writer import FileWriter

__all__ = [
    # Client
    "FormsClient",
    "PullResult",
    "PushResult",
    # Transport
    "FormTransport",
    "GoogleFormsTransport",
    "LocalFileTransport",
    # Diff
    "DiffResult",
    "ItemChange",
    "diff_forms",
    # Request generation
    "generate_requests",
    # File operations
    "FormTransformer",
    "FileWriter",
    "read_current_files",
    "extract_pristine",
    # Exceptions
    "ExtraFormError",
    "TransportError",
    "AuthenticationError",
    "NotFoundError",
    "DiffError",
    "MissingPristineError",
    "InvalidFileError",
]
