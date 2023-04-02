# Copyright 2022 MOSEC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Exceptions used in the Worker.

Suppose the input dataflow of our model server is as follows:

**bytes** ``->`` *deserialize* ``->`` **data** ``->`` *parse* ``->`` **valid data**

If the raw bytes cannot be successfully deserialized, the `DecodingError`
is raised; if the decoded data cannot pass the validation check (usually
implemented by users), the `ValidationError` should be raised.
"""

from mosec.protocol import HTTPStautsCode


class MosecError(Exception):
    """Mosec basic exception."""

    code = HTTPStautsCode.INTERNAL_ERROR
    msg = "mosec error"


class ClientError(MosecError):
    """Client side error.

    This error indicates that the server cannot or will not process the request
    due to something that is perceived to be a client error. It will return the
    details to the client side with
    `HTTP 400 <https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400>`__.
    """

    code = HTTPStautsCode.BAD_REQUEST
    msg = "bad request"


class ServerError(MosecError):
    """Server side error.

    This error indicates that the server encountered an unexpected condition
    that prevented it from fulfilling the request. It will return the details
    to the client side with
    `HTTP 500 <https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500>`__.

    Attention: be careful about the returned message since it may contain some
    sensitive information. If you don't want to return the details, just raise
    an exception that is not inherited from `mosec.errors.MosecError`.
    """

    code = HTTPStautsCode.INTERNAL_ERROR
    msg = "internal error"


class EncodingError(ServerError):
    """Serialization error.

    The `EncodingError` should be raised in user-implemented codes when
    the serialization for the response bytes fails. This error will set
    to status code to
    `HTTP 500 <https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500>`__
    and show the details in the response.
    """

    msg = "encoding error"


class DecodingError(ClientError):
    """De-serialization error.

    The `DecodingError` should be raised in user-implemented codes
    when the de-serialization for the request bytes fails. This error
    will set the status code to
    `HTTP 400 <https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400>`__
    in the response.
    """

    msg = "decoding error"


class ValidationError(MosecError):
    """Request data validation error.

    The `ValidationError` should be raised in user-implemented codes,
    where the validation for the input data fails. Usually, it should be
    put after the data de-serialization, which converts the raw bytes
    into structured data. This error will set the status code to
    `HTTP 422 <https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/422>`__
    in the response.
    """

    code = HTTPStautsCode.VALIDATION_ERROR
    msg = "request validation error"


class MosecTimeoutError(BaseException):
    """Exception raised when a MOSEC worker operation times out.

    If a bug in the forward code causes the worker to hang indefinitely, a timeout
    can be used to ensure that the worker eventually returns control to the main
    thread program. When a timeout occurs, the `MosecTimeout` exception is raised.
    This exception can be caught and handled appropriately to perform any necessary
    cleanup tasks or return a response indicating that the operation timed out.

    Note that `MosecTimeout` is a subclass of `BaseException`, not `Exception`.
    This is because timeouts should not be caught and handled in the same way as
    other exceptions. Instead, they should be handled in a separate `except` block
    which isn't designed to break the working loop.
    """

    code = HTTPStautsCode.TIMEOUT_ERROR
    msg = "mosec timeout error"
