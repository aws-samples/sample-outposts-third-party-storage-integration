"""
Data manipulation and search utility functions.
"""

from typing import Any, Callable, Dict, List, Optional, TypeVar


def find_first_by_property(items: List[Dict[str, Any]], key: str, value: Any) -> Optional[Dict[str, Any]]:
    """
    Returns the first dictionary in a list where the specified key has the given value.

    Args:
        items: A list of dictionaries to search.
        key: The dictionary key to look for.
        value: The value to match against.

    Returns:
        The first matching dictionary, or None if no match is found.
    """

    return next((item for item in items if item.get(key) == value), None)


def snake_to_camel(snake_str: str) -> str:
    """
    Convert snake_case string to camelCase.

    Args:
        snake_str: The snake_case string to convert.

    Returns:
        The camelCase string.

    Examples:
        >>> snake_to_camel("auth_secret_name")
        'authSecretName'
        >>> snake_to_camel("simple_key")
        'simpleKey'
        >>> snake_to_camel("already_camel")
        'alreadyCamel'
    """

    components = snake_str.split("_")
    return components[0] + "".join(word.capitalize() for word in components[1:])


T = TypeVar("T")


def transform_keys(data: T, key_transform_func: Callable[[str], str]) -> T:
    """
    Recursively transform all string keys in a dictionary using the provided transformation function.

    Args:
        data: The data structure to transform (dict, list, or other).
        key_transform_func: Function to apply to string keys.

    Returns:
        The transformed data structure with keys converted, maintaining the same type as input.

    Examples:
        >>> data = {"auth_secret_name": "secret", "nested_dict": {"inner_key": "value"}}
        >>> transform_keys(data, snake_to_camel)
        {'authSecretName': 'secret', 'nestedDict': {'innerKey': 'value'}}
    """

    if isinstance(data, dict):
        transformed_dict = {}
        for key, value in data.items():
            # Transform the key if it's a string
            new_key = key_transform_func(key) if isinstance(key, str) else key
            # Recursively transform the value
            transformed_dict[new_key] = transform_keys(value, key_transform_func)
        return transformed_dict  # type: ignore
    elif isinstance(data, list):
        # Recursively transform each item in the list
        return [transform_keys(item, key_transform_func) for item in data]  # type: ignore
    else:
        # Return the data as-is if it's not a dict or list
        return data
