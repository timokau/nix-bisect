class ResourceConstraintException(Exception):
    """An operation cannot be executed within a resource limit."""

    pass


class TooManyBuildsException(ResourceConstraintException):
    """An operation would need more rebuilds than allowed."""

    pass
