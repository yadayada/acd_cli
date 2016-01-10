from datetime import datetime, timedelta


def datetime_to_timestamp(dt: datetime) -> float:
    return (dt - datetime(1970, 1, 1)) / timedelta(seconds=1)
