import asyncio
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jarvix_logic import jarvix_main_router

app = FastAPI(title="Jarvix AI Assistant")

# Mount the 'static' directory to serve CSS and JS files.
app.mount("/static", StaticFiles(directory="static"), name="static")


class ConnectionManager:
    """Manages active WebSocket connections and their respective command queues."""

    def __init__(self):
        self.active_connections: dict[WebSocket, asyncio.Queue] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = asyncio.Queue()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    async def get_queue(self, websocket: WebSocket) -> asyncio.Queue | None:
        return self.active_connections.get(websocket)


manager = ConnectionManager()


async def command_consumer(websocket: WebSocket):
    """
    A background task that runs for each user, processing commands from their queue one by one.
    """
    queue = await manager.get_queue(websocket)
    if not queue:
        return

    while True:
        try:
            command_id, prompt = await queue.get()
            await websocket.send_json({"type": "start_processing", "id": command_id})

            # The router now handles all complex logic, including sending stream messages by itself.
            async for log_message in jarvix_main_router(prompt, websocket, command_id):
                # Only send non-empty log messages here. Streams are handled by the agent.
                if log_message:
                    await websocket.send_json(
                        {"type": "log", "id": command_id, "message": log_message}
                    )

            await websocket.send_json({"type": "end_processing", "id": command_id})
            queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception:
            # This general exception ensures that if one command fails, the consumer for this user doesn't crash.
            pass


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serves the main single-page application HTML file."""
    # To keep things clean, we will use a proper templating engine approach,
    # but for a single page, reading the file directly is simple and effective.
    with open("templates/index.html") as f:
        return HTMLResponse(content=f.read())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handles the persistent WebSocket connection for each user."""
    await manager.connect(websocket)
    consumer_task = asyncio.create_task(command_consumer(websocket))
    try:
        while True:
            # Wait for a new command from the user's frontend
            data = await websocket.receive_json()
            queue = await manager.get_queue(websocket)
            if queue:
                # Add the command to this user's queue
                await queue.put((data["id"], data["prompt"]))
    except WebSocketDisconnect:
        # Clean up when the user closes the browser tab
        manager.disconnect(websocket)
        consumer_task.cancel()
