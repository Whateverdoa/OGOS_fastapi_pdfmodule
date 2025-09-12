from typing import Union


def route_by_winding(winding_value: int) -> int:
    """
    Route based on winding value according to the specified rules.

    Args:
        winding_value: The input value to match against routing rules

    Returns:
        int: The route value (0, 90, 180, or 270)

    Raises:
        ValueError: If no matching route is found
    """
    routing_table = {
        1: 180,
        2: 0,
        3: 90,
        4: 270,
        5: 0,
        6: 0,
        7: 0,
        8: 0,
    }

    if winding_value in routing_table:
        return routing_table[winding_value]
    else:
        raise ValueError(f"No matching route for winding value: {winding_value}")


def route_by_winding_str(winding_value: Union[str, int]) -> int:
    """
    Route based on winding value (string or numeric) according to the specified rules.

    Args:
        winding_value: The input value to match against routing rules (can be string or int)

    Returns:
        int: The route value (0, 90, 180, or 270)

    Raises:
        ValueError: If no matching route is found
    """
    routing_table = {
        "1": 180,
        "2": 0,
        "3": 90,
        "4": 270,
        "5": 0,
        "6": 0,
        "7": 0,
        "8": 0,
        1: 180,
        2: 0,
        3: 90,
        4: 270,
        5: 0,
        6: 0,
        7: 0,
        8: 0,
    }

    if winding_value in routing_table:
        return routing_table[winding_value]

    # Fallback: attempt normalization (strip, cast to int then map)
    try:
        normalized = int(str(winding_value).strip())
        return route_by_winding(normalized)
    except Exception:
        raise ValueError(f"Error: No matching route for winding value: {winding_value}")

