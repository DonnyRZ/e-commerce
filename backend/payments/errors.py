"""CLICK Shop API protocol error codes (from the official CLICK reference).

Internal domain logic may raise richer errors; callback responses must map
to these exact protocol codes.
"""

SUCCESS = 0
SIGNATURE_FAILED = -1
INCORRECT_AMOUNT = -2
INVALID_ACTION = -3
ALREADY_PAID = -4
ORDER_NOT_FOUND = -5
TRANSACTION_NOT_FOUND = -6
UPDATE_FAILURE = -7
INVALID_REQUEST = -8
TRANSACTION_CANCELLED = -9


class ClickProtocolError(Exception):
    def __init__(self, code: int, note: str):
        super().__init__(note)
        self.code = code
        self.note = note
