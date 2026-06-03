def test_package_import_exposes_version_metadata() -> None:
    import harnessci

    assert isinstance(harnessci.__version__, str)
    assert harnessci.__version__
