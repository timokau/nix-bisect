class ResourceConstraintException(Exception):
    """An operation cannot be executed within a resource limit."""

    pass


class TooManyBuildsException(ResourceConstraintException):
    """An operation would need more rebuilds than allowed."""

    pass


class BlacklistedBuildsException(ResourceConstraintException):
    """An operation would need to rebuild a blacklisted drv"""

    def __init__(self, drvs):
        super().__init__(f"Blacklisted Builds: {drvs}")
