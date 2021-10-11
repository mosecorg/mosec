"""
Suppose the input dataflow of our model server is as follows:

**bytes** --- *deserialize*<sup>(decoding)</sup> ---> **data**
--- *parse*<sup>(validation)</sup> ---> **valid data**

If the raw bytes cannot be successfully deserialized, the `DecodingError`
is raised; if the decoded data cannot pass the validation check (usually
implemented by users), the `ValidationError` should be raised.
"""


class DecodingError(Exception):
    """
    The `DecodingError` should be raised in user-implemented codes
    when the de-serialization for the request bytes fails. This error
    will set the status code to
    [HTTP 400]("https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400)
    in the response.
    """


class ValidationError(Exception):
    """
    The `ValidationError` should be raised in user-implemented codes,
    where the validation for the input data fails. Usually, it should be
    put after the data de-serialization, which converts the raw bytes
    into structured data. This error will set the status code to
    [HTTP 422](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/422)
    in the response.
    """
