### File: `tele-downloader-toolkit/utils/async_helpers.py`
# tele-downloader-toolkit/utils/async_helpers.py

import asyncio
import threading
from typing import Callable, Any, Coroutine, Optional
import functools
import time


def run_async_in_thread(coro_func: Callable[..., Coroutine[Any, Any, Any]], *args: Any,
                        **kwargs: Any) -> threading.Thread:
    """
    Runs an asynchronous coroutine function in a new dedicated thread with its own event loop.
    Returns the Thread object. The thread will start immediately.
    """

    def thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(coro_func(*args, **kwargs))
        except Exception as e:
            print(f"Error in async thread: {e}")
        finally:
            loop.close()

    thread = threading.Thread(target=thread_target, daemon=True)
    thread.start()
    return thread


def run_on_main_thread(root_widget: Any, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """
    Schedules a callback function to be executed on the main Tkinter/CustomTkinter thread.
    This is crucial for safely updating GUI widgets from background threads.

    Args:
        root_widget: The main Tkinter/CustomTkinter window or any widget
                     that has an 'after' method (e.g., self.root in your app.py).
        callback: The function to execute on the main thread.
        *args, **kwargs: Arguments to pass to the callback.
    """
    safe_callback = functools.partial(callback, *args, **kwargs)
    root_widget.after(0, safe_callback)


async def _example_async_task(name: str, delay: int):
    print(f"Async task {name} started in thread: {threading.current_thread().name}")
    await asyncio.sleep(delay)
    print(f"Async task {name} finished in thread: {threading.current_thread().name}")


def _test_async_helpers():
    print(f"Main thread: {threading.current_thread().name}")

    thread1 = run_async_in_thread(_example_async_task, "Task 1", 3)
    thread2 = run_async_in_thread(_example_async_task, "Task 2", 1)

    print("Background tasks launched. Main thread continuing...")

    time.sleep(0.5)
    print("Main thread done with its immediate work.")


if __name__ == "__main__":
    _test_async_helpers()
    print("Main script exiting.")