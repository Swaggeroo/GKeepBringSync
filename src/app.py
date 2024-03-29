import logging
import os
import time
from datetime import datetime
from typing import List, Optional

import gkeepapi
import schedule
from decouple import config
from python_bring_api.bring import Bring

# Constants
GOOGLE_EMAIL: str = config("GOOGLE_EMAIL")
GOOGLE_PASSWORD: str = config("GOOGLE_PASSWORD")
BRING_EMAIL: str = config("GOOGLE_EMAIL")
BRING_PASSWORD: str = config("BRING_PASSWORD")
KEEP_LIST_ID: str = config("KEEP_LIST_ID")
SYNC_MODE: int = config("SYNC_MODE", default="0", cast=int)
TIMEOUT: int = config("TIMEOUT", default="60", cast=int)
BRING_LIST_NAME: Optional[str] = config("BRING_LIST_NAME", default=None)
GOOGLE_TOKEN: Optional[str] = config("GOOGLE_TOKEN", default=None)

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# init services
gkeepapi.node.DEBUG = True
keep = gkeepapi.Keep()
bring = Bring(BRING_EMAIL, BRING_PASSWORD)


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
        keep.resume(GOOGLE_EMAIL, token)
        token = keep.getMasterToken()
    elif GOOGLE_TOKEN:
        logging.info("Using provided google token")
        keep.resume(GOOGLE_EMAIL, GOOGLE_TOKEN)
        token = keep.getMasterToken()
    else:
        logging.info("Getting new google token")
        keep.login(GOOGLE_EMAIL, GOOGLE_PASSWORD)
        token = keep.getMasterToken()

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
    name: str, keep_list: gkeepapi.node.List
) -> Optional[gkeepapi.node.ListItem]:
    """
    Returns the unchecked item with the provided name from the Google Keep list.
    If no such item exists, it returns None.
    :param name: The name of the item to get.
    :param keep_list: The Google Keep list to get the item from.
    :return: The unchecked item with the provided name, or None if no such item exists.
    """
    for item in keep_list.unchecked:
        if item.text == name:
            return item
    return None


def delete_duplicates(keep_list: gkeepapi.node.List) -> None:
    """
    Deletes duplicate items from the provided Google Keep list.
    :param keep_list: The Google Keep list to delete duplicates from.
    """
    items = getAllItemsKeep(keep_list)
    for item in items:
        if items.count(item) > 1:
            logging.info(f"Deleting duplicate item: {item}")
            get_keep_list_item(item, keep_list).delete()
            items.remove(item)


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


def getAllItemsBring(bring_list: dict) -> List[str]:
    """
    Returns all items in the provided Bring list.
    :param bring_list: The Bring list to get items from.
    :return: A list of all items in the Bring list.
    """
    items = bring.getItems(bring_list["listUuid"])
    return [item["name"] for item in items["purchase"]]


def getAllItemsKeep(keep_list: gkeepapi.node.List) -> List[str]:
    """
    Returns all unchecked items in the provided Google Keep note.
    :param keep_list: The Google Keep note to get items from.
    :return: A list of all unchecked items in the Google Keep note.
    """
    return [item.text for item in keep_list.unchecked]


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

    bring_items = getAllItemsBring(bring_list)
    keep_items = getAllItemsKeep(keep_list)

    if SYNC_MODE == 0:
        cached_list = load_cached_list()
        if cached_list is None:
            cached_list = list(set(bring_items) | set(keep_items))
            save_list(cached_list)
            apply_list(cached_list, bring_list, keep_list)
            return None
        for item in keep_items:
            if item not in bring_items and item not in cached_list:
                bring_items.append(item)
                cached_list.append(item)
            elif item not in bring_items:
                cached_list.remove(item)
            elif item in bring_items and item not in cached_list:
                cached_list.append(item)
        for item in bring_items:
            if item not in keep_items and item not in cached_list:
                keep_items.append(item)
                cached_list.append(item)
            elif item not in keep_items:
                cached_list.remove(item)
            elif item in keep_items and item not in cached_list:
                cached_list.append(item)
        save_list(cached_list)
        apply_list(cached_list, bring_list, keep_list)
    elif SYNC_MODE == 1:
        apply_list(bring_items, bring_list, keep_list)
    elif SYNC_MODE == 2:
        apply_list(keep_items, bring_list, keep_list)

    keep.sync()


def load_cached_list() -> Optional[List[str]]:
    """
    Loads the cached list from a file.
    Returns the list if it exists, otherwise returns None.
    """
    if os.path.exists("./data/list.txt"):
        with open("./data/list.txt", "r", encoding="utf-8") as f:
            keep_list = f.read().split("\n")
        return keep_list
    else:
        return None


def save_list(new_list: List[str]) -> None:
    """
    Saves the provided list to a file.
    :param new_list: The list to save.
    """
    new_list = clean_list(new_list)
    with open("./data/list.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(new_list))


def apply_list(
    new_list: List[str], bring_list: dict, keep_list: gkeepapi.node.List
) -> None:
    """
    Applies the provided list to the Google Keep and Bring lists.
    :param new_list: The list to apply.
    :param bring_list: The Bring list to apply the new list to.
    :param keep_list: The Google Keep list to apply the new list to.
    """
    new_list = clean_list(new_list)

    # bring
    bring_items = getAllItemsBring(bring_list)
    for item in bring_items:
        if item not in new_list:
            logging.info(f"Deleting item from bring: {item}")
            bring.removeItem(
                bring_list["listUuid"], item.encode("utf-8").decode("ISO-8859-9")
            )
    for item in new_list:
        if item not in bring_items:
            logging.info(f"Adding item to bring: {item}")
            bring.saveItem(
                bring_list["listUuid"], item.encode("utf-8").decode("ISO-8859-9")
            )

    # keep
    keep_items = getAllItemsKeep(keep_list)
    for item in keep_items:
        if item not in new_list:
            logging.info(f"Deleting item from keep: {item}")
            get_keep_list_item(item, keep_list).delete()
    for item in new_list:
        if item not in keep_items:
            logging.info(f"Adding item to keep: {item}")
            keep_list.add(
                item.encode("utf-8").decode("utf-8"),
                False,
                gkeepapi.node.NewListItemPlacementValue.Bottom,
            )

def clean_list(list: List[str]) -> List[str]:
    """
    Cleans the list from empty items.
    :param list: The list to clean.
    :return: The cleaned list.
    """
    return [item for item in list if item]

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

sync(keepList, bringList)

if TIMEOUT != 0:
    logging.info(f"Starting scheduler run every {TIMEOUT} minutes")
    schedule.every(TIMEOUT).minutes.do(sync, keepList, bringList)
    while True:
        schedule.run_pending()
        time.sleep(1)
