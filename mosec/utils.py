import abc
from typing import Callable, Generic, TypeVar, Union

T = TypeVar("T")


class _Uninitialized:
    pass


class DeferredBase(Generic[T], abc.ABC):
    @abc.abstractmethod
    def initialize(self) -> T:
        """Deferred initialization"""


class Deferred(DeferredBase[T]):
    def __init__(self, constructor: Callable[..., T], *args, **kwargs) -> None:
        self._constructor = constructor
        self._args = args
        self._kwargs = kwargs
        self._deferred_object: Union[_Uninitialized, T] = _Uninitialized()

    def initialize(self) -> T:
        if isinstance(self._deferred_object, _Uninitialized):
            try:
                self._deferred_object = self._constructor(*self._args, **self._kwargs)
            except Exception as err:
                raise RuntimeError(err)
        return self._deferred_object
