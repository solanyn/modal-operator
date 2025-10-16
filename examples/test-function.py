def hello_world(name: str = "World"):
    """Simple test function for Modal."""
    return f"Hello, {name}! This is a Modal function."


def add_numbers(a: int, b: int):
    """Simple math function."""
    return {"result": a + b, "operation": "addition"}


if __name__ == "__main__":
    print(hello_world("Modal"))
    print(add_numbers(5, 3))
