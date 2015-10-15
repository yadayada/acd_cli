import requests
import re

from requests.exceptions import ConnectionError

try:
    from requests.exceptions import ReadTimeout as ReadTimeoutError
except ImportError:
    try:
        from requests.packages.urllib3.exceptions import ReadTimeoutError
    except ImportError:
        class ReadTimeoutError(Exception):
            pass

# status codes that indicate request success
OK_CODES = [requests.codes.OK]


class RequestError(Exception):
    """Catch-all exception class for various connection and ACD server errors."""

    class CODE(object):
        CONN_EXCEPTION = 1000
        FAILED_SUBREQUEST = 1002
        INCOMPLETE_RESULT = 1003
        REFRESH_FAILED = 1004
        INVALID_TOKEN = 1005

    codes = requests.codes

    def __init__(self, status_code: int, msg: str):
        self.status_code = status_code
        if msg:
            self.msg = msg
        else:
            self.msg = '[acd_api] no body received.'

    def __str__(self):
        return 'RequestError: ' + str(self.status_code) + ', ' + self.msg


def catch_conn_exception(func):
    """Request connection exception decorator
    :raises RequestError"""

    def decorated(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ConnectionError, ReadTimeoutError) as e:
            raise RequestError(RequestError.CODE.CONN_EXCEPTION, e.__str__())

    return decorated


def is_valid_id(id: str) -> bool:
    return bool(id) and len(id) == 22 and re.match('^[a-zA-Z0-9_-]*$', id)
