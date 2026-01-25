from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from .web3_client import Web3Client

T = TypeVar("T")


@dataclass
class TransactionMined(Generic[T]):
    receipt: Dict[str, Any]
    result: T


class TransactionHandle(Generic[T]):
    """
    Transaction lifecycle handle (submitted-by-default).

    - `tx_hash` is available immediately after submission.
    - `wait_mined` / `wait_confirmed` can be called to await a receipt (and optional confirmations)
      and produce a domain result.
    """

    def __init__(
        self,
        *,
        web3_client: Web3Client,
        tx_hash: str,
        compute_result: Callable[[Dict[str, Any]], T],
    ):
        self.web3_client = web3_client
        self.tx_hash = tx_hash
        self._compute_result = compute_result
        self._memo: Dict[str, TransactionMined[T]] = {}

    def wait_mined(
        self,
        *,
        timeout: int = 60,
        confirmations: int = 1,
        throw_on_revert: bool = True,
    ) -> TransactionMined[T]:
        key = f"{timeout}:{confirmations}:{int(bool(throw_on_revert))}"
        existing = self._memo.get(key)
        if existing is not None:
            return existing

        receipt = self.web3_client.wait_for_transaction(
            self.tx_hash,
            timeout=timeout,
            confirmations=confirmations,
            throw_on_revert=throw_on_revert,
        )
        result = self._compute_result(receipt)
        mined = TransactionMined(receipt=receipt, result=result)
        self._memo[key] = mined
        return mined

    def wait_confirmed(
        self,
        *,
        timeout: int = 60,
        confirmations: int = 1,
        throw_on_revert: bool = True,
    ) -> TransactionMined[T]:
        return self.wait_mined(timeout=timeout, confirmations=confirmations, throw_on_revert=throw_on_revert)


