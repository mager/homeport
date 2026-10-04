import asyncio
import json
from contextlib import suppress
from typing import Callable

from websockets.asyncio.client import unix_connect

from .models import Config, Event


class RpcError(RuntimeError):
    pass


class RPC:
    def __init__(self, config: Config, on_event: Callable[[Event], None]):
        self.config, self.on_event = config, on_event
        self.pending = {}
        self.sequence = 0

    async def __aenter__(self):
        self.ws = await unix_connect(
            str(self.config.socket), uri="ws://localhost", max_size=32 * 1024 * 1024
        )
        self.reader = asyncio.create_task(self.read())
        try:
            await self.call(
                "initialize",
                {
                    "clientInfo": {
                        "name": "magerbot_pydantic",
                        "title": "Magerbot",
                        "version": "0.1.0",
                    }
                },
            )
            await self.ws.send(json.dumps({"method": "initialized"}))
        except BaseException:
            await self.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(self, *_):
        await self.ws.close()
        self.reader.cancel()
        with suppress(asyncio.CancelledError):
            await self.reader

    async def call(self, method, params=None):
        self.sequence += 1
        request_id = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.ws.send(
                json.dumps({"id": request_id, "method": method, "params": params or {}})
            )
            return await asyncio.wait_for(future, self.config.rpc_timeout)
        finally:
            self.pending.pop(request_id, None)

    async def read(self):
        error = ConnectionError("app-server disconnected")
        try:
            async for raw in self.ws:
                message = json.loads(raw)
                if "method" in message:
                    self.on_event(
                        Event(
                            method=message["method"],
                            params=message.get("params") or {},
                            request_id=message.get("id"),
                        )
                    )
                    if "id" in message:
                        # Full access avoids command approvals. Unknown interactive requests
                        # fail explicitly instead of silently granting permissions or hanging.
                        await self.ws.send(
                            json.dumps(
                                {
                                    "id": message["id"],
                                    "error": {
                                        "code": -32601,
                                        "message": "Interactive request unsupported by magerbot; use attached TUI",
                                    },
                                }
                            )
                        )
                elif (
                    future := self.pending.get(message.get("id"))
                ) and not future.done():
                    if "error" in message:
                        future.set_exception(RpcError(str(message["error"])))
                    else:
                        future.set_result(message.get("result", {}))
        except Exception as exc:
            error = exc
        finally:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(error)
