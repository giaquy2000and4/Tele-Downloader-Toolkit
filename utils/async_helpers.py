# tele-downloader-toolkit/utils/async_helpers.py

import asyncio
import threading
from typing import Callable, Any, Coroutine, Optional
import functools  # Used for functools.partial to wrap callbacks


# You might need to import customtkinter or tkinter here if you want to
# provide a default 'root' object or specific GUI-related helpers.
# For now, we'll assume the 'root' object is passed.
# from customtkinter import CTk # Example, if needed


def run_async_in_thread(coro_func: Callable[..., Coroutine[Any, Any, Any]], *args: Any,
                        **kwargs: Any) -> threading.Thread:
    """
    Runs an asynchronous coroutine function in a new dedicated thread with its own event loop.
    Returns the Thread object. The thread will start immediately.
    """

    def thread_target():
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Run the coroutine until it completes
            loop.run_until_complete(coro_func(*args, **kwargs))
        except Exception as e:
            print(f"Error in async thread: {e}")
            # You might want to log this error to a GUI log or propagate it
            # For GUI, consider using run_on_main_thread to display an error dialog.
        finally:
            loop.close()
            # print(f"Event loop in thread '{threading.current_thread().name}' closed.") # For debugging

    thread = threading.Thread(target=thread_target, daemon=True)  # daemon=True means thread exits with main program
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
    # Use functools.partial to bind the callback and its arguments
    # This creates a new callable object that, when called, will execute callback(*args, **kwargs)
    # This is safer than lambda for tkinter.after as lambda can capture mutable state.
    safe_callback = functools.partial(callback, *args, **kwargs)
    root_widget.after(0, safe_callback)  # Schedule to run as soon as possible on the main thread


# Example usage (for testing purposes, not part of the module's public API directly)
async def _example_async_task(name: str, delay: int):
    print(f"Async task {name} started in thread: {threading.current_thread().name}")
    await asyncio.sleep(delay)
    print(f"Async task {name} finished in thread: {threading.current_thread().name}")


def _test_async_helpers():
    print(f"Main thread: {threading.current_thread().name}")

    # Run an async task in a new thread
    thread1 = run_async_in_thread(_example_async_task, "Task 1", 3)
    thread2 = run_async_in_thread(_example_async_task, "Task 2", 1)

    # In a real GUI app, you'd have self.root here
    # For this simple test, we'll simulate a main loop exit
    print("Background tasks launched. Main thread continuing...")

    # Simulate some main thread work
    time.sleep(0.5)
    print("Main thread done with its immediate work.")

    # To ensure daemon threads have a chance to finish, or if main thread does nothing
    # time.sleep(4) # Uncomment this if you want to see both tasks complete before main exits


if __name__ == "__main__":
    import time

    _test_async_helpers()
    # The main script will exit here. Daemon threads will be terminated.
    # If using Tkinter, root.mainloop() would keep the main thread alive.
    print("Main script exiting.")