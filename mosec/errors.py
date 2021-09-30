class ValidationError(Exception):
    """
    The `ValidationError` should be raised in user-implemented codes,
    where the validation for the input data fails. Usually it can be put
    after the data deserialization, which converts the raw bytes into
    structured data.
    """
