"""Keep admission slots until executor work has actually stopped."""
import asyncio


async def await_owned(future):
    """Cancellation waits for the underlying work, then propagates.

    Cancelling an asyncio wrapper cannot stop a running executor job. This
    helper also handles repeated cancellation while the job is draining.
    """
    future = asyncio.ensure_future(future)
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        while not future.done():
            try:
                await asyncio.shield(future)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not future.cancelled():
            future.exception()
        raise


async def run_in_executor_owned(executor, function, *args):
    return await await_owned(
        asyncio.get_running_loop().run_in_executor(executor, function, *args)
    )
