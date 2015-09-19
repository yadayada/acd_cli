from unittest import TestLoader, TestSuite

from .test_actions import ActionTestCase
from .test_api import APITestCase
from .test_cache import CacheTestCase
from .test_helper import HelperTestCase


def get_suite() -> TestSuite:
    """"Returns a suite of all automated tests."""
    all_tests = TestSuite()

    all_tests.addTest(TestLoader().loadTestsFromTestCase(ActionTestCase))
    all_tests.addTest(TestLoader().loadTestsFromTestCase(APITestCase))
    all_tests.addTest(TestLoader().loadTestsFromTestCase(CacheTestCase))
    all_tests.addTest(TestLoader().loadTestsFromTestCase(HelperTestCase))

    return all_tests
