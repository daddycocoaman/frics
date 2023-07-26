from rich import traceback

try:
    import uvloop  # type: ignore

    uvloop.install()
except ImportError:
    pass

traceback.install(show_locals=True)
