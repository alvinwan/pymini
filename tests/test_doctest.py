import doctest

import pymini.pymini
import pymini.utils


def test_pymini_doctests():
    result = doctest.testmod(pymini.pymini, verbose=False)
    assert result.failed == 0


def test_utils_doctests():
    result = doctest.testmod(pymini.utils, verbose=False)
    assert result.failed == 0
