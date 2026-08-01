import sys
import unittest
from unittest.mock import MagicMock

# Mock missing third-party dependencies if not installed
for mod in ["gkeepapi", "gkeepapi.node", "schedule", "decouple", "python_bring_api", "python_bring_api.bring"]:
    if mod not in sys.modules:
        try:
            __import__(mod)
        except ImportError:
            m = MagicMock()
            sys.modules[mod] = m

from src.app import (
    ShoppingItem,
    parse_specification,
    parse_bring_specification,
    format_specification,
    extract_amount_from_title,
    parse_keep_item,
    format_keep_item,
    delete_duplicates,
    shopping_item_key,
    build_bring_items,
    merge_duplicates,
)


class TestGKeepBringSync(unittest.TestCase):

    def test_parse_specification(self):
        self.assertEqual(parse_specification(""), (1, ""))
        self.assertEqual(parse_specification("2"), (2, ""))
        self.assertEqual(parse_specification("2 Organic"), (2, "Organic"))
        self.assertEqual(parse_specification("15 2L Milk"), (15, "2L Milk"))
        self.assertEqual(parse_specification("For the car"), (1, "For the car"))

    def test_parse_bring_specification(self):
        self.assertEqual(parse_bring_specification(""), [(1, "")])
        self.assertEqual(parse_bring_specification("2"), [(2, "")])
        self.assertEqual(parse_bring_specification("2 Bio"), [(2, "Bio")])
        self.assertEqual(parse_bring_specification("2 Bio + 4 Bio"), [(2, "Bio"), (4, "Bio")])
        self.assertEqual(parse_bring_specification("2 + 4 Bio"), [(2, ""), (4, "Bio")])
        self.assertEqual(parse_bring_specification("Salt + Pepper"), [(1, "Salt + Pepper")])

    def test_format_specification(self):
        self.assertEqual(format_specification(1, ""), "")
        self.assertEqual(format_specification(2, ""), "2")
        self.assertEqual(format_specification(2, "Organic"), "2 Organic")
        self.assertEqual(format_specification(15, "2L Milk"), "15 2L Milk")

    def test_extract_amount_from_title(self):
        self.assertEqual(extract_amount_from_title("Milk"), ("Milk", 1))
        self.assertEqual(extract_amount_from_title("2 Milk"), ("Milk", 2))
        self.assertEqual(extract_amount_from_title("2x Milk"), ("Milk", 2))
        self.assertEqual(extract_amount_from_title("15 2L Milk"), ("2L Milk", 15))
        # Ensure quantity words 'Ein', 'Eine', 'One', 'Two', 'Zwei', 'Drei' extract item name and quantity
        self.assertEqual(extract_amount_from_title("Ein Apfel"), ("Apfel", 1))
        self.assertEqual(extract_amount_from_title("Eine Flasche Milch"), ("Flasche Milch", 1))
        self.assertEqual(extract_amount_from_title("One Milk"), ("Milk", 1))
        self.assertEqual(extract_amount_from_title("Two Milk"), ("Milk", 2))
        self.assertEqual(extract_amount_from_title("Zwei Flaschen"), ("Flaschen", 2))
        self.assertEqual(extract_amount_from_title("Drei Packungen"), ("Packungen", 3))
        # Ensure trailing model numbers are NOT parsed as quantity
        self.assertEqual(extract_amount_from_title("iPhone 15"), ("iPhone 15", 1))
        self.assertEqual(extract_amount_from_title("Studio 54"), ("Studio 54", 1))

    def test_parse_keep_item(self):
        item1 = parse_keep_item("Milk")
        self.assertEqual(item1.name, "Milk")
        self.assertEqual(item1.amount, 1)
        self.assertEqual(item1.comment, "")

        item2 = parse_keep_item("Milk (2)")
        self.assertEqual(item2.name, "Milk")
        self.assertEqual(item2.amount, 2)
        self.assertEqual(item2.comment, "")

        item3 = parse_keep_item("Milk (2 Bio)")
        self.assertEqual(item3.name, "Milk")
        self.assertEqual(item3.amount, 2)
        self.assertEqual(item3.comment, "Bio")

        item4 = parse_keep_item("Eine Flasche Milch (Bio)")
        self.assertEqual(item4.name, "Flasche Milch")
        self.assertEqual(item4.amount, 1)
        self.assertEqual(item4.comment, "Bio")

        item5 = parse_keep_item("iPhone 15 (2)")
        self.assertEqual(item5.name, "iPhone 15")
        self.assertEqual(item5.amount, 2)
        self.assertEqual(item5.comment, "")

    def test_format_keep_item(self):
        self.assertEqual(format_keep_item(ShoppingItem("Milk", 1, "")), "Milk")
        self.assertEqual(format_keep_item(ShoppingItem("Milk", 2, "")), "Milk (2)")
        self.assertEqual(format_keep_item(ShoppingItem("Milk", 2, "Bio")), "Milk (2 Bio)")

    def test_merge_duplicates(self):
        items = [
            ShoppingItem("Milk", 1, ""),
            ShoppingItem("Milk", 2, ""),
            ShoppingItem("Apples", 3, "Organic"),
        ]
        merged = merge_duplicates(items)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].name, "Milk")
        self.assertEqual(merged[0].amount, 3)
        self.assertEqual(merged[1].name, "Apples")
        self.assertEqual(merged[1].amount, 3)

    def test_build_bring_items(self):
        items = [
            ShoppingItem("Milk", 2, ""),
            ShoppingItem("Milk", 4, "Bio"),
            ShoppingItem("Milk", 3, "Oat"),
        ]
        bring_items = build_bring_items(items)
        self.assertEqual(len(bring_items), 1)
        self.assertEqual(bring_items[0].name, "Milk")
        self.assertEqual(bring_items[0].comment, "2 + 4 Bio + 3 Oat")

    def test_non_destructive_delete_duplicates(self):
        item_a1 = MagicMock()
        item_a1.text = "Milk"

        item_a2 = MagicMock()
        item_a2.text = "Milk (2)"

        item_b = MagicMock()
        item_b.text = "Bread"

        keep_list = MagicMock()
        keep_list.unchecked = [item_a1, item_a2, item_b]

        delete_duplicates(keep_list)

        self.assertEqual(item_a1.text, "Milk (3)")
        item_a2.delete.assert_called_once()
        self.assertEqual(item_b.text, "Bread")
        item_b.delete.assert_not_called()
