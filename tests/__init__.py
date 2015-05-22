from unittest import TestLoader

from .test_api import APITestCase

def get_suite():
    return TestLoader().loadTestsFromTestCase(APITestCase)