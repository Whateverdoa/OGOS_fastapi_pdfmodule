"""
Winding Value Routing Module

Provides functions for routing based on winding values according to specified rules.
Maps winding values to rotation angles (0°, 90°, 180°, 270°) for processing decisions.
"""


def route_by_winding(winding_value):
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
        # Inverted on the roll → mirror 1–4
        5: 180,  # like 1
        6: 0,    # like 2
        7: 90,   # inverted on the roll like 3
        8: 270,  # inverted on the roll like 4
    }
    
    if winding_value in routing_table:
        return routing_table[winding_value]
    else:
        raise ValueError(f"No matching route for winding value: {winding_value}")


def route_by_winding_str(winding_value):
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
        '1': 180,
        '2': 0,
        '3': 90,
        '4': 270,
        '5': 180,
        '6': 0,
        '7': 90,
        '8': 270,
        1: 180,
        2: 0,
        3: 90,
        4: 270,
        5: 180,
        6: 0,
        7: 90,
        8: 270,
    }
    
    if winding_value in routing_table:
        return routing_table[winding_value]
    else:
        raise ValueError(f"Error: No matching route for winding value: {winding_value}")


if __name__ == "__main__":
    # Test cases
    test_values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]
    
    print("Testing route_by_winding:")
    for value in test_values:
        try:
            result = route_by_winding(value)
            print(f"Winding {value} → Route to {result}")
        except ValueError as e:
            print(f"Winding {value} → {e}")
    
    print("\nTesting route_by_winding_str:")
    test_str_values = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 1, 2, 3, 4]
    for value in test_str_values:
        try:
            result = route_by_winding_str(value)
            print(f"Winding {value} → Route to {result}")
        except ValueError as e:
            print(f"Winding {value} → {e}")
