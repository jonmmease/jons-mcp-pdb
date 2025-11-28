"""Custom exception classes for jons-mcp-pdb."""


class PdbError(Exception):
    """Base exception for pdb-related errors."""

    pass


class PdbSessionError(PdbError):
    """Exception for session-related errors."""

    def __init__(self, message: str, session_id: str | None = None):
        self.session_id = session_id
        super().__init__(message)


class PdbCommandError(PdbError):
    """Exception for command execution errors."""

    def __init__(self, message: str, command: str | None = None):
        self.command = command
        super().__init__(message)


class PdbNotInitializedError(PdbError):
    """Exception when accessing an uninitialized session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(
            f"Session '{session_id}' is not initialized or has no active process"
        )


class InvalidBreakpointError(PdbError):
    """Exception for breakpoint-related errors."""

    def __init__(self, message: str, breakpoint_id: int | None = None):
        self.breakpoint_id = breakpoint_id
        super().__init__(message)
