"""Main entry point for Modal operator."""

import asyncio
import logging

from modal_operator.operator import main

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Run the operator
    asyncio.run(main())
