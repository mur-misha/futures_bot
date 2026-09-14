"""Backward-compatible entry point for V2."""
from main import run


if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
