class HarnessCIError(Exception):
    """Base exception for user-facing HarnessCI failures."""


class SpecParseError(HarnessCIError):
    pass
