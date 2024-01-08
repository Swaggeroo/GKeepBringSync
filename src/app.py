import logging
import os
import time
from datetime import datetime

import gkeepapi
import schedule
from decouple import config
from python_bring_api.bring import Bring

# Constants
GOOGLE_EMAIL = config("GOOGLE_EMAIL")
GOOGLE_PASSWORD = config("GOOGLE_PASSWORD")
BRING_EMAIL = config("GOOGLE_EMAIL")
BRING_PASSWORD = config("BRING_PASSWORD")
KEEP_LIST_ID = config("KEEP_LIST_ID")
SYNC_MODE = int(config("SYNC_MODE", default="0"))
TIMEOUT = int(config("TIMEOUT", default="60"))

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# init services
gkeepapi.node.DEBUG = True
keep = gkeepapi.Keep()
bring = Bring(BRING_EMAIL, BRING_PASSWORD)


def login():
    """
    Logs into the Bring and Google Keep services.
    """
    bring.login()

    if os.path.exists("./data/token.txt"):
        logging.info("Using cached google token")
        with open("./data/token.txt", "r") as f:
            token = f.read()
            f.close()
            os.remove("./data/token.txt")
            keep.resume(GOOGLE_EMAIL, token)
            token = keep.getMasterToken()
            with open("./data/token.txt", "w") as fnew:
                fnew.write(str(token))
    elif config("GOOGLE_TOKEN") is not None:
        logging.info("Using provided google token")
        keep.resume(GOOGLE_EMAIL, config("GOOGLE_TOKEN"))
        token = keep.getMasterToken()
        with open("./data/token.txt", "w") as f:
            f.write(str(token))
    else:
        logging.info("Getting new google token")
        keep.login(GOOGLE_EMAIL, GOOGLE_PASSWORD)
        token = keep.getMasterToken()
        with open("./data/token.txt", "w") as f:
            f.write(str(token))
    logging.info("Logged in")


def delete_old_items(note):
    """
    Deletes all checked items from the provided Google Keep note.
    :param note: The Google Keep note to delete items from.
    """
    for item in note.checked:
        logging.info("Deleting item: " + item.text)
        item.delete()


def get_keep_list_item(name, keep_list):
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


def delete_duplicates(keep_list):
    """
    Deletes duplicate items from the provided Google Keep list.
    :param keep_list: The Google Keep list to delete duplicates from.
    """
    items = getAllItemsKeep(keep_list)
    for item in items:
        if items.count(item) > 1:
            logging.info("Deleting duplicate item: " + item)
            get_keep_list_item(item, keep_list).delete()
            items.remove(item)


def get_bring_list(lists):
    """
    Returns the Bring list that matches the name provided in the environment variable 'BRING_LIST_NAME'.
    If 'BRING_LIST_NAME' is not set, it returns the first list.
    :param lists: The list of Bring lists.
    :return: The selected Bring list.
    """
    if config("BRING_LIST_NAME") is not None:
        for bring_list in lists:
            if bring_list["name"] == config("BRING_LIST_NAME"):
                return bring_list
    return lists[0]


def getAllItemsBring(bring_list):
    """
    Returns all items in the provided Bring list.
    :param bring_list: The Bring list to get items from.
    :return: A list of all items in the Bring list.
    """
    items = bring.getItems(bring_list["listUuid"])
    return [item["name"] for item in items["purchase"]]


def getAllItemsKeep(keep_list):
    """
    Returns all unchecked items in the provided Google Keep note.
    :param keep_list: The Google Keep note to get items from.
    :return: A list of all unchecked items in the Google Keep note.
    """
    return [item.text for item in keep_list.unchecked]


def sync(keep_list, bring_list):
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


def load_cached_list():
    """
    Loads the cached list from a file.
    Returns the list if it exists, otherwise returns None.
    """
    if os.path.exists("./data/list.txt"):
        with open("./data/list.txt", "r", encoding="utf-8") as f:
            keep_list = f.read().split("\n")
            f.close()
            return keep_list
    else:
        return None


def save_list(new_list):
    """
    Saves the provided list to a file.
    :param new_list: The list to save.
    """
    with open("./data/list.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(new_list))
        f.close()


def apply_list(new_list, bring_list, keep_list):
    """
    Applies the provided list to the Google Keep and Bring lists.
    :param new_list: The list to apply.
    :param bring_list: The Bring list to apply the new list to.
    :param keep_list: The Google Keep list to apply the new list to.
    """

    # bring
    bring_items = getAllItemsBring(bring_list)
    for item in bring_items:
        if item not in new_list:
            logging.info("Deleting item from bring: " + item)
            bring.removeItem(
                bring_list["listUuid"], item.encode("utf-8").decode("ISO-8859-9")
            )
    for item in new_list:
        if item not in bring_items:
            logging.info("Adding item to bring: " + item)
            bring.saveItem(
                bring_list["listUuid"], item.encode("utf-8").decode("ISO-8859-9")
            )

    # keep
    keep_items = getAllItemsKeep(keep_list)
    for item in keep_items:
        if item not in new_list:
            logging.info("Deleting item from keep: " + item)
            get_keep_list_item(item, keep_list).delete()
    for item in new_list:
        if item not in keep_items:
            logging.info("Adding item to keep: " + item)
            keep_list.add(
                item.encode("utf-8").decode("ISO-8859-9"),
                False,
                gkeepapi.node.NewListItemPlacementValue.Bottom,
            )


# Main
logging.info("Starting app")
logging.info("Sync mode: " + str(SYNC_MODE))
logging.info("Timeout: " + str(TIMEOUT) + " minutes")

login()

# load Keep
keep.sync()
keepList = keep.get(KEEP_LIST_ID)
logging.info("Keep list: " + keepList.title)

# load Bring
bringList = get_bring_list(bring.loadLists()["lists"])

sync(keepList, bringList)

if TIMEOUT != 0:
    logging.info("Starting scheduler run every " + str(TIMEOUT) + " minutes")
    schedule.every(TIMEOUT).minutes.do(sync, keepList, bringList)
    while True:
        schedule.run_pending()
        time.sleep(1)
