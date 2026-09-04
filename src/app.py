import asyncio
import logging
import os
import time
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass
from dataclasses import asdict
import json
import re

import aiohttp
import gkeepapi
import schedule
from decouple import config
from bring_api import Bring

# Constants
GOOGLE_EMAIL: str = config("GOOGLE_EMAIL")
BRING_EMAIL: str = config("BRING_EMAIL")
BRING_PASSWORD: str = config("BRING_PASSWORD")
KEEP_LIST_ID: str = config("KEEP_LIST_ID")
SYNC_MODE: int = config("SYNC_MODE", default="0", cast=int)
TIMEOUT: int = config("TIMEOUT", default="60", cast=int)
BRING_LIST_NAME: Optional[str] = config("BRING_LIST_NAME", default=None)
BRING_LANGUAGE_CODE: Optional[str] = config("BRING_LANGUAGE_CODE", default=None)
GOOGLE_TOKEN: Optional[str] = config("GOOGLE_TOKEN", default=None)

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# init services
gkeepapi.node.DEBUG = True
keep = gkeepapi.Keep() if callable(gkeepapi.Keep) else None


class BringClient:
    """Synchronous adapter around the asynchronous, localized Bring client."""

    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._session: aiohttp.ClientSession | None = None
        self._client: Bring | None = None

    def _run(self, coroutine):
        return self._loop.run_until_complete(coroutine)

    def _require_client(self) -> Bring:
        if self._client is None:
            raise RuntimeError("Bring client has not been logged in.")
        return self._client

    def login(self) -> None:
        async def _login() -> None:
            self._session = aiohttp.ClientSession()
            self._client = Bring(self._session, self._email, self._password)
            await self._client.login()

        self._run(_login())

    def loadLists(self) -> dict:
        lists = self._run(self._require_client().load_lists())
        return {
            "lists": [
                {"listUuid": item.listUuid, "name": item.name}
                for item in lists.lists
            ]
        }

    def getItems(self, list_uuid: str) -> dict:
        items = self._run(self._require_client().get_list(list_uuid))
        return {
            "purchase": [
                {
                    "name": item.itemId,
                    "specification": item.specification,
                }
                for item in items.items.purchase
            ]
        }

    def saveItem(
        self, list_uuid: str, item_name: str, specification: str = ""
    ) -> None:
        self._run(
            self._require_client().save_item(list_uuid, item_name, specification)
        )

    def removeItem(self, list_uuid: str, item_name: str) -> None:
        self._run(self._require_client().remove_item(list_uuid, item_name))

    def close(self) -> None:
        if self._session is not None and not self._session.closed:
            self._run(self._session.close())
        if not self._loop.is_closed():
            self._loop.close()

    def setListArticleLanguage(self, list_uuid: str, language_code: str) -> None:
        async def _set_language() -> None:
            client = self._require_client()
            await client.set_list_article_language(list_uuid, language_code)
            await client.reload_user_list_settings()
            await client.reload_article_translations()

        self._run(_set_language())


bring = BringClient(BRING_EMAIL, BRING_PASSWORD) if callable(Bring) else None
@dataclass
class ShoppingItem:
    """
    Represents a shopping list item independent of Google Keep or Bring.
    """
    name: str
    amount: int = 1
    comment: str = ""
    original_name: str | None = None

    def specification(self) -> str:
        return format_specification(self.amount, self.comment)


def parse_specification(specification: str) -> tuple[int, str]:
    """
    Parses a Bring specification into quantity and comment.

    Rules:
    - A leading number is interpreted as the quantity.
    - Any following text is treated as the comment.
    - If no leading number exists, the quantity defaults to 1.

    Examples:
        ""                -> (1, "")
        "2"               -> (2, "")
        "2 Organic"       -> (2, "Organic")
        "15 2L Milk"      -> (15, "2L Milk")
        "For the car"     -> (1, "For the car")
    """

    specification = specification.strip()

    if specification == "":
        return 1, ""

    match = re.match(r"^(\d+)\s*(.*)$", specification)

    if match:
        amount = int(match.group(1))
        comment = match.group(2).strip()
        return amount, comment

    return 1, specification

def parse_bring_specification(specification: str) -> list[tuple[int, str]]:
    """
    Parses a Bring specification into one or more quantity/comment pairs.

    Bring merges duplicate items using " + ". Each merged part is returned
    separately if parts match merged quantity specifications.

    Examples:
        ""                  -> [(1, "")]
        "2"                 -> [(2, "")]
        "2 Bio"             -> [(2, "Bio")]
        "2 Bio + 4 Bio"     -> [(2, "Bio"), (4, "Bio")]
        "2 + 4 Bio"         -> [(2, ""), (4, "Bio")]
        "Bio + 2 Bio"       -> [(1, "Bio"), (2, "Bio")]
        "Salt + Pepper"     -> [(1, "Salt + Pepper")]

    :param specification: The Bring specification.
    :return: A list of quantity/comment pairs.
    """

    spec = specification.strip()
    if not spec:
        return [(1, "")]

    parts = spec.split(" + ")
    if len(parts) > 1 and any(re.match(r"^\d+", p.strip()) for p in parts):
        return [parse_specification(part.strip()) for part in parts]

    return [parse_specification(spec)]

def format_specification(amount: int, comment: str) -> str:
    """
    Creates a normalized Bring specification.

    Rules:
    - Quantity 1 without a comment becomes an empty specification.
    - Quantity only is stored as the number.
    - Quantity and comment are separated by exactly one space.

    Examples:
        (1, "")             -> ""
        (2, "")             -> "2"
        (2, "Organic")      -> "2 Organic"
        (15, "2L Milk")     -> "15 2L Milk"
    """

    comment = comment.strip()

    if amount <= 1 and comment == "":
        return ""

    if comment == "":
        return "" if amount <= 1 else str(amount)

    if amount <= 1:
        return comment

    return f"{amount} {comment}"

def parse_keep_item(text: str) -> ShoppingItem:
    """
    Parses a Google Keep entry into a ShoppingItem.

    Supported formats:
        Milk
        Milk (2)
        Milk (2 Organic)
        Milk (15 2L)

    Only the last parentheses pair is interpreted as metadata.
    """

    text = text.strip()

    match = re.match(r"^(.*?)\s*\((.*)\)$", text)

    if not match:
        name, amount = extract_amount_from_title(text)

        return ShoppingItem(
            name=name,
            amount=amount,
            original_name=name,
        )

    title_part = match.group(1).strip()
    spec_part = match.group(2).strip()

    name, title_amount = extract_amount_from_title(title_part)
    spec_amount, comment = parse_specification(spec_part)

    if title_amount > 1 and spec_amount > 1:
        final_amount = title_amount + spec_amount - 1
    elif spec_amount > 1:
        final_amount = spec_amount
    else:
        final_amount = title_amount

    return ShoppingItem(
        name=name,
        amount=final_amount,
        comment=comment,
        original_name=name,
    )

def format_keep_item(item: ShoppingItem) -> str:
    """
    Converts a ShoppingItem into a Google Keep entry.
    """

    specification = format_specification(
        item.amount,
        item.comment,
    )

    if specification == "":
        return item.name

    return f"{item.name} ({specification})"


def login() -> None:
    """
    Logs into the Bring and Google Keep services.
    """
    bring.login()

    token_file_path = "./data/token.txt"

    if os.path.exists(token_file_path):
        logging.info("Using cached google token")
        with open(token_file_path, "r") as f:
            token = f.read()
        os.remove(token_file_path)
        if not token:
            logging.fatal("Google token is empty. Please provide a valid token.")
            exit(1)
        keep.authenticate(GOOGLE_EMAIL, token)
        token = keep.getMasterToken()
    elif GOOGLE_TOKEN:
        logging.info("Using provided google token")
        keep.authenticate(GOOGLE_EMAIL, GOOGLE_TOKEN)
        token = keep.getMasterToken()
    else:
        logging.fatal("Google token not found. Please provide a token. See README.md for more information.")
        exit(1)

    logging.info("Saving google token")
    with open(token_file_path, "w") as f:
        f.write(str(token))

    logging.info("Logged in")


def delete_old_items(note: gkeepapi.node.TopLevelNode) -> None:
    """
    Deletes all checked items from the provided Google Keep note.
    :param note: The Google Keep note to delete items from.
    """
    for item in note.checked:
        logging.info(f"Deleting item: {item.text}")
        item.delete()


def get_keep_list_item(
    item: ShoppingItem,
    keep_list: gkeepapi.node.List,
) -> Optional[gkeepapi.node.ListItem]:
    """
    Returns the Google Keep list item matching the provided ShoppingItem.
    :param item: The shopping item to search for.
    :param keep_list: The Google Keep list.
    :return: The matching Google Keep list item or None.
    """

    for keep_item in keep_list.unchecked:

        parsed = parse_keep_item(keep_item.text)

        if (
            normalize_name(parsed.name)
            == normalize_name(item.name)
            and normalize_comment(parsed.comment)
            == normalize_comment(item.comment)
        ):
            return keep_item

    return None


def delete_duplicates(keep_list: gkeepapi.node.List) -> None:
    """
    Merges duplicate Google Keep items with the same name and comment in-place.
    Quantities are summed while preserving item placement and avoiding deletion of unique items.
    :param keep_list: The Google Keep list to merge.
    """

    grouped: dict[tuple[str, str], list[tuple[gkeepapi.node.ListItem, ShoppingItem]]] = {}

    for keep_item in list(keep_list.unchecked):
        parsed = parse_keep_item(keep_item.text)
        key = shopping_item_key(parsed)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append((keep_item, parsed))

    for items in grouped.values():
        if len(items) <= 1:
            continue

        first_keep_item, first_parsed = items[0]
        total_amount = sum(parsed.amount for _, parsed in items)

        merged_item = ShoppingItem(
            name=first_parsed.name,
            amount=total_amount,
            comment=first_parsed.comment,
        )

        new_text = format_keep_item(merged_item)
        if first_keep_item.text != new_text:
            first_keep_item.text = new_text

        for duplicate_keep_item, _ in items[1:]:
            logging.info(f"Deleting duplicate Keep item: {duplicate_keep_item.text}")
            duplicate_keep_item.delete()


def get_bring_list(lists: List[dict]) -> dict:
    """
    Returns the Bring list that matches the name provided in the environment variable 'BRING_LIST_NAME'.
    If 'BRING_LIST_NAME' is not set, it returns the first list.
    :param lists: The list of Bring lists.
    :return: The selected Bring list.
    """
    if BRING_LIST_NAME:
        for bring_list in lists:
            if bring_list["name"] == BRING_LIST_NAME:
                return bring_list
    return lists[0]


def getAllItemsBring(bring_list: dict) -> list[ShoppingItem]:
    """
    Returns all items in the provided Bring list.
    :param bring_list: The Bring list to get items from.
    :return: A list of ShoppingItems.
    """

    items = bring.getItems(bring_list["listUuid"])

    result: list[ShoppingItem] = []

    for item in items["purchase"]:

        for amount, comment in parse_bring_specification(
            item["specification"]
        ):

            parsed_name, title_amount = extract_amount_from_title(
                item["name"]
            )

            result.append(
                ShoppingItem(
                    name=parsed_name,
                    original_name=item["name"],
                    amount=amount + title_amount - 1,
                    comment=comment,
                )
            )

    return result

def get_bring_item(
    name: str,
    comment: str,
    bring_items: list[ShoppingItem],
) -> Optional[ShoppingItem]:
    """
    Returns the Bring item matching the provided name and comment.
    :param name: The item name.
    :param comment: The item comment.
    :param bring_items: The list of Bring items.
    :return: The matching ShoppingItem or None.
    """

    for item in bring_items:
        if (
            normalize_name(item.name) == normalize_name(name)
            and normalize_comment(item.comment) == normalize_comment(comment)
        ):
            return item

    return None


def getAllItemsKeep(keep_list: gkeepapi.node.List) -> list[ShoppingItem]:
    """
    Returns all unchecked items in the provided Google Keep note.
    :param keep_list: The Google Keep note to get items from.
    :return: A list of ShoppingItems.
    """

    result: list[ShoppingItem] = []

    for item in keep_list.unchecked:
        result.append(parse_keep_item(item.text))

    return result

def get_keep_item(
    name: str,
    comment: str,
    keep_items: list[ShoppingItem],
) -> Optional[ShoppingItem]:
    """
    Returns the Google Keep item matching the provided name and comment.
    :param name: The item name.
    :param comment: The item comment.
    :param keep_items: The list of Google Keep items.
    :return: The matching ShoppingItem or None.
    """

    for item in keep_items:
        if (
            normalize_name(item.name) == normalize_name(name)
            and normalize_comment(item.comment) == normalize_comment(comment)
        ):
            return item

    return None

def shopping_item_equal(
    item1: ShoppingItem,
    item2: ShoppingItem,
) -> bool:
    """
    Compares two shopping items.
    :param item1: The first item.
    :param item2: The second item.
    :return: True if both items are equal.
    """

    return (
        item1.amount == item2.amount
        and normalize_comment(item1.comment) == normalize_comment(item2.comment)
    )

def copy_item(item: ShoppingItem) -> ShoppingItem:
    """
    Creates a copy of a shopping item.
    :param item: The item to copy.
    :return: A copied ShoppingItem.
    """

    return ShoppingItem(
        name=item.name,
        amount=item.amount,
        comment=item.comment,
        original_name=item.original_name,
    )
    
def merge_duplicates(
    items: list[ShoppingItem],
) -> list[ShoppingItem]:
    """
    Merges ShoppingItems with the same name and comment by summing
    their quantities.
    """

    merged: dict[tuple[str, str], ShoppingItem] = {}

    for item in items:

        key = shopping_item_key(item)

        if key not in merged:
            merged[key] = copy_item(item)
        else:
            merged[key].amount += item.amount

    return list(merged.values())

def build_bring_items(
    items: list[ShoppingItem],
) -> list[ShoppingItem]:
    """
    Merges ShoppingItems with the same name into the representation required
    by the Bring API.

    Different comments are stored inside one Bring specification separated
    by " + ".

    Example:

        Milk (2)
        Milk (4 Bio)
        Milk (3 Oat)

    becomes

        Milk (2 + 4 Bio + 3 Oat)

    :param items: Shopping items.
    :return: Shopping items formatted for Bring.
    """

    grouped: dict[tuple[str, str], ShoppingItem] = {}

    for item in items:

        key = (
            normalize_name(item.name),
            normalize_comment(item.comment),
        )

        if key not in grouped:
            grouped[key] = copy_item(item)
        else:
            grouped[key].amount += item.amount

    merged: dict[str, ShoppingItem] = {}

    for item in grouped.values():

        key = normalize_name(item.name)

        part = item.specification()

        if key not in merged:

            merged[key] = ShoppingItem(
                name=item.name,
                amount=1,
                comment=part,
                original_name=item.original_name,
            )

            continue

        if part:

            if merged[key].comment:
                merged[key].comment += " + " + part
            else:
                merged[key].comment = part

    return list(merged.values())

def shopping_item_key(item: ShoppingItem) -> tuple[str, str]:
    """
    Returns the unique key of a shopping item.
    :param item: The shopping item.
    :return: A tuple containing the normalized name and comment.
    """

    return (
        normalize_name(item.name),
        normalize_comment(item.comment),
    )

def normalize_name(name: str) -> str:
    """
    Returns a normalized item name.
    Comparison is case-insensitive and ignores leading/trailing whitespace.
    :param name: The item name.
    :return: The normalized name.
    """

    return " ".join(name.strip().lower().split())

def normalize_comment(comment: str) -> str:
    """
    Returns a normalized item comment.
    :param comment: The item comment.
    :return: The normalized comment.
    """

    return " ".join(comment.strip().lower().split())

NUMBER_WORDS = {
    # English
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    # German
    "ein": 1,
    "eine": 1,
    "eins": 1,
    "zwei": 2,
    "drei": 3,
    "vier": 4,
    "fünf": 5,
    "fuenf": 5,
    "sechs": 6,
    "sieben": 7,
    "acht": 8,
    "neun": 9,
    "zehn": 10,
    "elf": 11,
    "zwölf": 12,
}


def extract_amount_from_title(title: str) -> tuple[str, int]:
    """
    Extracts a quantity from the beginning of a title if specified as a number,
    digit prefix, or number word.

    Supported examples:
        "2 Milk"           -> ("Milk", 2)
        "2x Milk"          -> ("Milk", 2)
        "Two Milk"         -> ("Milk", 2)
        "Ein Apfel"        -> ("Apfel", 1)
        "Eine Flasche"     -> ("Flasche", 1)
        "Zwei Flaschen"    -> ("Flaschen", 2)
        "iPhone 15"        -> ("iPhone 15", 1)

    If no leading quantity is found, the original title and quantity 1 are returned.

    :param title: The item title.
    :return: A tuple containing the cleaned title and extracted quantity.
    """

    title_clean = title.strip()
    words = title_clean.split()

    if len(words) <= 1:
        return title_clean, 1

    first = words[0].lower()
    match = re.match(r"^(\d+)x?$", first)
    if match:
        amount = int(match.group(1))
        rest = " ".join(words[1:]).strip()
        if rest:
            return rest, amount

    if first in NUMBER_WORDS:
        rest = " ".join(words[1:]).strip()
        if rest:
            return rest, NUMBER_WORDS[first]

    return title_clean, 1

def get_all_keys(
    keep_items: list[ShoppingItem],
    bring_items: list[ShoppingItem],
    cached_items: list[ShoppingItem],
) -> list[tuple[str, str]]:
    """
    Returns every unique shopping item key.
    :param keep_items: Google Keep items.
    :param bring_items: Bring items.
    :param cached_items: Cached items.
    :return: A sorted list of unique keys.
    """

    keys = set()

    for item in keep_items:
        keys.add(shopping_item_key(item))

    for item in bring_items:
        keys.add(shopping_item_key(item))

    for item in cached_items:
        keys.add(shopping_item_key(item))

    return sorted(keys)


def sync(keep_list: gkeepapi.node.List, bring_list: dict) -> None:
    """
    Synchronizes the provided Google Keep and Bring lists
    based on the sync mode set in the environment variable 'SYNC_MODE'.
    :param keep_list: The Google Keep list to synchronize.
    :param bring_list: The Bring list to synchronize.
    """

    logging.info("Syncing lists " + str(datetime.now()))

    keep.sync()

    delete_old_items(keep_list)
    delete_duplicates(keep_list)

    keep.sync()

    raw_bring_items = getAllItemsBring(bring_list)
    bring_items = merge_duplicates(raw_bring_items)

    keep_items = merge_duplicates(
        getAllItemsKeep(keep_list)
    )

    if SYNC_MODE == 0:

        cached_list = load_cached_list()
        if cached_list is not None:
            cached_list = merge_duplicates(cached_list)

        if cached_list is None:
            cached_list = []

        new_list: list[ShoppingItem] = []

        for name, comment in get_all_keys(
            keep_items,
            bring_items,
            cached_list,
        ):

            keep_item = get_keep_item(
                name,
                comment,
                keep_items,
            )
            bring_item = get_bring_item(
                name,
                comment,
                bring_items,
            )
            cached_item = get_bring_item(
                name,
                comment,
                cached_list,
            )

            logging.info(
                f"{name} ({comment}): "
                f"K={keep_item is not None} "
                f"B={bring_item is not None} "
                f"C={cached_item is not None}"
            )
            
            # New item in Google Keep
            if (
                keep_item is not None
                and bring_item is None
                and cached_item is None
            ):
                new_list.append(copy_item(keep_item))
                continue

            # New item in Bring
            if (
                bring_item is not None
                and keep_item is None
                and cached_item is None
            ):
                new_list.append(copy_item(bring_item))
                continue

            # Deleted in Google Keep
            if (
                keep_item is None
                and bring_item is not None
                and cached_item is not None
            ):
                logging.info(f"{name}: Deleted in Google Keep")
                # Nicht zu new_list hinzufügen -> apply_list löscht es aus Bring
                continue

            # Deleted in Bring
            if (
                bring_item is None
                and keep_item is not None
                and cached_item is not None
            ):
                logging.info(f"{name}: Deleted in Bring")
                # Nicht zu new_list hinzufügen -> apply_list löscht es aus Keep
                continue

            # Unchanged item
            if (
                keep_item is not None
                and bring_item is not None
                and cached_item is not None
                and shopping_item_equal(keep_item, bring_item)
                and shopping_item_equal(keep_item, cached_item)
            ):
                new_list.append(copy_item(keep_item))
                continue

            # Changed in Google Keep
            if (
                keep_item is not None
                and bring_item is not None
                and cached_item is not None
                and not shopping_item_equal(keep_item, cached_item)
                and shopping_item_equal(bring_item, cached_item)
            ):
                logging.info(
                    f"{format_keep_item(keep_item)}: Google Keep changed"
                )

                new_list.append(copy_item(keep_item))
                continue

            # Changed in Bring
            if (
                keep_item is not None
                and bring_item is not None
                and cached_item is not None
                and shopping_item_equal(keep_item, cached_item)
                and not shopping_item_equal(bring_item, cached_item)
            ):
                logging.info(
                    f"{format_keep_item(bring_item)}: Bring changed"
                )

                new_list.append(copy_item(bring_item))
                continue
            
            # Conflict
            if (
                keep_item is not None
                and bring_item is not None
                and cached_item is not None
                and not shopping_item_equal(keep_item, cached_item)
                and not shopping_item_equal(bring_item, cached_item)
            ):
                logging.warning(f"{format_keep_item(keep_item)}: Conflict detected, keeping Google Keep version")

                new_list.append(copy_item(keep_item))
                continue

        save_list(new_list)
        apply_list(new_list, bring_list, keep_list)

    elif SYNC_MODE == 1:
        apply_list(bring_items, bring_list, keep_list)

    elif SYNC_MODE == 2:
        apply_list(keep_items, bring_list, keep_list)

    keep.sync()


def load_cached_list() -> Optional[list[ShoppingItem]]:
    """
    Loads the cached list from a file.
    :return: A list of ShoppingItems if the cache exists, otherwise None.
    """

    if not os.path.exists("./data/list.json"):
        return None

    with open("./data/list.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    result: list[ShoppingItem] = []

    for item in data:
        result.append(
            ShoppingItem(
                name=item["name"],
                amount=item["amount"],
                comment=item["comment"],
                original_name=item.get("original_name"),
            )
        )

    return result


def save_list(new_list: list[ShoppingItem]) -> None:
    """
    Saves the provided list to a file.
    :param new_list: The list to save.
    """

    with open("./data/list.json", "w", encoding="utf-8") as f:
        json.dump(
            [asdict(item) for item in new_list],
            f,
            indent=4,
            ensure_ascii=False,
        )


def apply_list(
    new_list: list[ShoppingItem],
    bring_list: dict,
    keep_list: gkeepapi.node.List,
) -> None:
    """
    Applies the provided list to the Google Keep and Bring lists.
    :param new_list: The list to apply.
    :param bring_list: The Bring list to apply the new list to.
    :param keep_list: The Google Keep list to apply the new list to.
    """

    # Bring
    raw_bring_items = getAllItemsBring(bring_list)
    bring_items = merge_duplicates(raw_bring_items)

    bring_new_items = build_bring_items(new_list)
    bring_current_items = build_bring_items(bring_items)
    
    def raw_signature(name: str) -> list[tuple[int, str]]:
        entries = []

        for item in raw_bring_items:
            current_name, title_amount = extract_amount_from_title(item.original_name)

            if normalize_name(current_name) != normalize_name(name):
                continue

            entries.append(
                (
                    item.amount + title_amount - 1,
                    normalize_comment(item.comment),
                )
            )

        entries.sort()
        return entries


    def new_signature(name: str) -> list[tuple[int, str]]:
        entries = []

        for item in new_list:
            if normalize_name(item.name) != normalize_name(name):
                continue

            entries.append(
                (
                    item.amount,
                    normalize_comment(item.comment),
                )
            )

        entries.sort()
        return entries
    
    changed_names = set()

    all_names = set()

    for item in raw_bring_items:
        all_names.add(normalize_name(item.name))

    for item in bring_new_items:
        all_names.add(normalize_name(item.name))

    for name in all_names:

        if raw_signature(name) != new_signature(name):
            changed_names.add(name)
    
    for name in changed_names:

        logging.info(f"Replacing Bring item: {name}")

        for current in list(raw_bring_items):

            current_name, _ = extract_amount_from_title(current.name)

            if normalize_name(current_name) != name:
                continue

            logging.info(f"Removing Bring item: {current.original_name}")

            bring.removeItem(
                bring_list["listUuid"],
                current.original_name,
            )
            time.sleep(1)

        for item in bring_new_items:

            if normalize_name(item.name) != name:
                continue

            bring.saveItem(
                bring_list["listUuid"],
                item.name,
                item.specification(),
            )
            time.sleep(1)

            break

    # Google Keep
    keep_items = getAllItemsKeep(keep_list)
    
    for item in keep_items:

        if get_keep_item(
            item.name,
            item.comment,
            new_list,
        ) is None:

            logging.info(
                f"Deleting item from Google Keep: {item.name}"
            )

            keep_item = get_keep_list_item(
                item,
                keep_list,
            )

            if keep_item is not None:
                keep_item.delete()
    
    for item in new_list:

        existing = get_keep_item(
            item.name,
            item.comment,
            keep_items,
        )

        if existing is None:
            logging.info(f"Adding item to Google Keep: {item.name}")

            keep_list.add(
                format_keep_item(item),
                False,
                gkeepapi.node.NewListItemPlacementValue.Bottom,
            )

            continue

        if not shopping_item_equal(existing, item):

            logging.info(
                f"Updating Google Keep item: {item.name}"
            )

            keep_item = get_keep_list_item(
                existing,
                keep_list,
            )

            if keep_item is not None:
                keep_item.text = format_keep_item(item)
            else:
                keep_list.add(
                    format_keep_item(item),
                    False,
                    gkeepapi.node.NewListItemPlacementValue.Bottom,
                )

if __name__ == "__main__":
    try:
        # Main
        logging.info("Starting app")
        logging.info(f"Sync mode: {SYNC_MODE}")
        logging.info(f"Timeout: {TIMEOUT} minutes")

        login()

        # load Keep
        keep.sync()
        keepList = keep.get(KEEP_LIST_ID)
        logging.info(f"Keep list: {keepList.title}")

        # load Bring
        bringList = get_bring_list(bring.loadLists()["lists"])
        if BRING_LANGUAGE_CODE:
            logging.info(f"Setting Bring article language to: {BRING_LANGUAGE_CODE}")
            bring.setListArticleLanguage(bringList["listUuid"], BRING_LANGUAGE_CODE)
        else:
            logging.info("Using existing Bring list article language")

        sync(keepList, bringList)

        if TIMEOUT != 0:
            logging.info(f"Starting scheduler run every {TIMEOUT} minutes")
            schedule.every(TIMEOUT).minutes.do(sync, keepList, bringList)
            while True:
                schedule.run_pending()
                time.sleep(1)
    finally:
        if bring is not None:
            bring.close()
