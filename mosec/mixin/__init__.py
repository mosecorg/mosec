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

"""Provide useful mixin to extend MOSEC."""

from mosec.mixin.msgpack_worker import MsgpackMixin
from mosec.mixin.numbin_worker import NumBinIPCMixin
from mosec.mixin.plasma_worker import PlasmaShmIPCMixin
from mosec.mixin.redis_worker import RedisShmIPCMixin
from mosec.mixin.typed_worker import TypedMsgPackMixin

__all__ = [
    "MsgpackMixin",
    "NumBinIPCMixin",
    "PlasmaShmIPCMixin",
    "TypedMsgPackMixin",
    "RedisShmIPCMixin",
]
