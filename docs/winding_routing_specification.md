# Winding Value Routing Specification

## Overview
The `route_by_winding` functions provide deterministic routing based on winding values, mapping specific input values to rotation angles (0°, 90°, 180°, 270°).

## Function Specifications

### `route_by_winding(winding_value)`

**Purpose**: Maps integer winding values to rotation angles for routing decisions.

**Input**:
- `winding_value` (int): Integer value from 1-8

**Output**:
- `int`: Rotation angle in degrees (0, 90, 180, or 270)

**Routing Table**:
```
Winding Value → Route Angle
1 → 180°
2 → 0°
3 → 90°
4 → 270°
5 → 0°
6 → 0°
7 → 0°
8 → 0°
```

**Error Handling**:
- Raises `ValueError` for any input not in the routing table
- Error message format: `"No matching route for winding value: {value}"`

### `route_by_winding_str(winding_value)`

**Purpose**: Maps string or integer winding values to rotation angles.

**Input**:
- `winding_value` (str | int): String or integer value from '1'-'8' or 1-8

**Output**:
- `int`: Rotation angle in degrees (0, 90, 180, or 270)

**Routing Table**: Same mapping as above, supports both string and integer inputs

**Error Handling**:
- Raises `ValueError` for any input not in the routing table
- Error message format: `"Error: No matching route for winding value: {value}"`

## Behavioral Requirements

1. **Deterministic**: Same input always produces same output
2. **Fail-fast**: Invalid inputs immediately raise `ValueError`
3. **Type flexibility**: String version accepts both string and numeric inputs
4. **Performance**: O(1) lookup time using dictionary
5. **Immutable**: Routing table cannot be modified at runtime

## Usage Constraints

- Input values must be exactly 1-8 (no ranges, decimals, or other values)
- Output angles are limited to 90-degree increments only
- Functions are stateless and thread-safe

## Implementation Location

The winding routing functions are implemented in `app/utils/winding_router.py`.

## Testing

Test cases should cover:
- All valid inputs (1-8, '1'-'8')
- Invalid inputs (0, 9, negative numbers, non-numeric strings)
- Type mixing (string and integer inputs for the flexible version)
- Error message formatting