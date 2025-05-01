import asyncio
import contextlib
import signal
from eventsourcingdb.client import Client
from eventsourcingdb.handlers.read_events import ReadEventsOptions


async def read_events_with_timeout(client, subject, timeout=5.0):
    """Read events with a timeout, demonstrating cancellation."""
    try:
        # Use asyncio.wait_for to implement a timeout
        await asyncio.wait_for(
            process_events(client, subject),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        print(f"Reading events timed out after {timeout} seconds")


async def process_events(client, subject):
    """Process events from the subject."""
    print(f"Starting to read events from {subject}")
    
    # Using contextlib.aclosing ensures the generator is closed properly
    # even if we exit the context due to an exception
    async with contextlib.aclosing(
        client.read_events(
            subject=subject,
            options=ReadEventsOptions(recursive=True)
        )
    ) as events:
        # Process events until something stops the operation
        count = 0
        async for event in events:
            count += 1
            print(f"Processed event #{count}: {event.type}")
            
            # Example condition to stop processing
            if count >= 10:
                print("Reached maximum event count, stopping")
                break
                
    print("Finished processing events")


async def cancel_after_delay(task, delay=2.0):
    """Cancel a task after a delay."""
    await asyncio.sleep(delay)
    print(f"Cancelling task after {delay} seconds")
    task.cancel()


async def main():
    # Create client
    client = Client(
        base_url="http://localhost:8080",
        api_token="your-api-token"
    )
    
    try:
        await client.initialize()
        
        # Example 1: Using asyncio.wait_for with a timeout
        print("\n--- Example 1: Reading with timeout ---")
        await read_events_with_timeout(client, "/users", timeout=3.0)
        
        # Example 2: Create a task and cancel it explicitly
        print("\n--- Example 2: Manual cancellation ---")
        event_task = asyncio.create_task(process_events(client, "/orders"))
        cancel_task = asyncio.create_task(cancel_after_delay(event_task, 2.0))
        
        try:
            await event_task
        except asyncio.CancelledError:
            print("Event reading was cancelled")
        
        await cancel_task
        
    finally:
        await client.close()

