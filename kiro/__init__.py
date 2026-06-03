from importlib.metadata import version, PackageNotFoundError
try:
    __version__ = version("kiro-gateway")
except PackageNotFoundError:
    __version__ = "2.1.0"
