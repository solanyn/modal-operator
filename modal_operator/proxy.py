#!/usr/bin/env python3
"""
Modal operator proxy to connect Modal workloads to cluster services via TCP.
Runs as a pod in the cluster and provides proxy access to cluster services.
"""

import asyncio
import logging
import socket
import struct
from typing import Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModalOperatorProxy:
    def __init__(self, host="0.0.0.0", port=1080):
        self.host = host
        self.port = port

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        try:
            # Modal operator proxy handshake
            if not await self.modal_proxy_handshake(reader, writer):
                return

            # Modal operator proxy connect request
            target_host, target_port = await self.modal_proxy_connect_request(
                reader, writer
            )
            if not target_host:
                return

            logger.info(f"Connecting to {target_host}:{target_port}")

            # Connect to target (cluster service)
            try:
                target_reader, target_writer = await asyncio.open_connection(
                    target_host, target_port
                )
            except Exception as e:
                logger.error(f"Failed to connect to {target_host}:{target_port}: {e}")
                # Send connection refused
                writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
                await writer.drain()
                return

            # Send success response
            writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            await writer.drain()

            # Start bidirectional forwarding
            await asyncio.gather(
                self.forward_data(reader, target_writer, "client->target"),
                self.forward_data(target_reader, writer, "target->client"),
                return_exceptions=True,
            )

        except Exception as e:
            logger.error(f"Client handling error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def modal_proxy_handshake(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> bool:
        # Read version and number of methods
        data = await reader.read(2)
        if len(data) != 2 or data[0] != 0x05:
            return False

        n_methods = data[1]
        methods = await reader.read(n_methods)

        # We support no authentication (0x00)
        if 0x00 in methods:
            writer.write(b"\x05\x00")  # Version 5, no auth
        else:
            writer.write(b"\x05\xff")  # No acceptable methods
            return False

        await writer.drain()
        return True

    async def modal_proxy_connect_request(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> Tuple[Optional[str], Optional[int]]:
        # Read connect request
        data = await reader.read(4)
        if len(data) != 4 or data[0] != 0x05 or data[1] != 0x01:  # Version 5, CONNECT
            return None, None

        atyp = data[3]  # Address type

        if atyp == 0x01:  # IPv4
            addr_data = await reader.read(4)
            host = socket.inet_ntoa(addr_data)
        elif atyp == 0x03:  # Domain name
            addr_len = (await reader.read(1))[0]
            addr_data = await reader.read(addr_len)
            host = addr_data.decode("utf-8")
        else:
            # Unsupported address type
            writer.write(
                b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00"
            )  # Address type not supported
            await writer.drain()
            return None, None

        # Read port
        port_data = await reader.read(2)
        port = struct.unpack(">H", port_data)[0]

        return host, port

    async def forward_data(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str
    ):
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception as e:
            logger.debug(f"Forward {direction} ended: {e}")
        finally:
            writer.close()

    async def start(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)

        logger.info(f"Modal operator proxy started on {self.host}:{self.port}")
        logger.info(
            "Modal workloads can connect via: modal-operator-proxy://proxy:1080"
        )

        async with server:
            await server.serve_forever()


async def main():
    proxy = ModalOperatorProxy()
    try:
        await proxy.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())
