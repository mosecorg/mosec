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

**bytes** --- *deserialize*<sup>(decoding)</sup> ---> **data**
--- *parse*<sup>(validation)</sup> ---> **valid data**

If the raw bytes cannot be successfully deserialized, the `DecodingError`
is raised; if the decoded data cannot pass the validation check (usually
implemented by users), the `ValidationError` should be raised.
"""


class EncodingError(Exception):
    """Serialization error.

    The `EncodingError` should be raised in user-implemented codes when
    the serialization for the response bytes fails. This error will set
    to status code to
    [HTTP 500](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500)
    in the response.
    """


class DecodingError(Exception):
    """De-serialization error.

    The `DecodingError` should be raised in user-implemented codes
    when the de-serialization for the request bytes fails. This error
    will set the status code to
    [HTTP 400]("https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400)
    in the response.
    """


class ValidationError(Exception):
    """Request data validation error.

    The `ValidationError` should be raised in user-implemented codes,
    where the validation for the input data fails. Usually, it should be
    put after the data de-serialization, which converts the raw bytes
    into structured data. This error will set the status code to
    [HTTP 422](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/422)
    in the response.
    """
