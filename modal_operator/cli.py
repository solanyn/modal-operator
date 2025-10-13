"""CLI interface for the Modal vGPU operator."""

import asyncio

import click

from modal_operator.operator import ModalClient


@click.group()
def cli():
    """Modal vGPU Operator CLI."""
    pass


@cli.command()
@click.option("--mock/--no-mock", default=False, help="Use mock Modal client")
def run(mock):
    """Run the operator."""
    import os

    if mock:
        os.environ["MODAL_MOCK"] = "true"

    from modal_operator.operator import kopf

    kopf.run()


@cli.command()
@click.argument("name")
@click.option("--image", default="python:3.11-slim", help="Container image")
@click.option("--command", default='echo "Hello from Modal!"', help="Command to run")
@click.option("--gpu", help="GPU specification (e.g., T4:1)")
@click.option("--mock/--no-mock", default=False, help="Use mock Modal client")
def test_modal(name, image, command, gpu, mock):
    """Test Modal integration."""

    async def _test():
        client = ModalClient(mock=mock)
        config = {"name": name, "image": image, "command": command, "cpu": "1.0", "memory": "512Mi"}
        if gpu:
            config["gpu"] = gpu

        app_id = await client.create_app(**config)
        click.echo(f"Created Modal app: {app_id}")

    asyncio.run(_test())


if __name__ == "__main__":
    cli()
