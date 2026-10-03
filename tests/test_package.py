import quorlo


def test_version_is_set():
    assert quorlo.__version__
    assert quorlo.__version__ != "0.0.0+unknown"
