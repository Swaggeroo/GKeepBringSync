import os
import gkeepapi
import schedule
import time
from python_bring_api.bring import Bring
from datetime import datetime

GOOGLE_EMAIL = os.environ['GOOGLE_EMAIL']
GOOGLE_PASSWORD = os.environ['GOOGLE_PASSWORD']
BRING_EMAIL = os.environ['GOOGLE_EMAIL']
BRING_PASSWORD = os.environ['BRING_PASSWORD']
KEEP_LIST_ID = os.environ['KEEP_LIST_ID']
SYNC_MODE = int(os.environ.get('SYNC_MODE', "0"))  # 0 = bidirectional, 1 = bring master, 2 = google master
TIMEOUT = int(os.environ.get('TIMEOUT', "60"))  # in minutes
# BRING_LIST_NAME

# if one is none quit
if (GOOGLE_EMAIL is None
        or GOOGLE_PASSWORD is None
        or BRING_EMAIL is None
        or BRING_PASSWORD is None
        or KEEP_LIST_ID is None):
    print("Please set all environment variables (see Repo)")
    exit(1)

gkeepapi.node.DEBUG = True
keep = gkeepapi.Keep()
bring = Bring(BRING_EMAIL, BRING_PASSWORD)


def login():
    bring.login()

    if os.path.exists('token.txt'):
        print("Using cached google token")
        with open('token.txt', 'r') as f:
            token = f.read()
            f.close()
            os.remove('token.txt')
            keep.resume(GOOGLE_EMAIL, token)
            token = keep.getMasterToken()
            with open('token.txt', 'w') as fnew:
                fnew.write(str(token))
    else:
        print("Getting new google token")
        keep.login(GOOGLE_EMAIL, GOOGLE_PASSWORD)
        token = keep.getMasterToken()
        with open('token.txt', 'w') as f:
            f.write(str(token))
    print("Logged in")


def delete_old_items(note):
    for item in note.checked:
        print('Deleting item: ' + item.text)
        item.delete()


def get_bring_list(lists):
    if os.environ.get('BRING_LIST_NAME') is not None:
        for bring_list in lists:
            if bring_list['name'] == os.environ.get('BRING_LIST_NAME'):
                return bring_list
    return lists[0]


def getAllItemsBring(bring_list):
    items = bring.getItems(bring_list['listUuid'])
    return [item['name'] for item in items['purchase']]


def getAllItemsKeep(note):
    return [item.text for item in note.unchecked]


def sync(keep_list, bring_list):
    print('Syncing lists ' + str(datetime.now()))
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
        for item in bring_items:
            if item not in keep_items and item not in cached_list:
                keep_items.append(item)
                cached_list.append(item)
            elif item not in keep_items:
                cached_list.remove(item)
        save_list(cached_list)
        apply_list(cached_list, bring_list, keep_list)
    elif SYNC_MODE == 1:
        apply_list(bring_items, bring_list, keep_list)
    elif SYNC_MODE == 2:
        apply_list(keep_items, bring_list, keep_list)

    keep.sync()


def load_cached_list():
    if os.path.exists('list.txt'):
        with open('list.txt', 'r', encoding="utf-8") as f:
            keep_list = f.read().split('\n')
            f.close()
            return keep_list
    else:
        return None


def save_list(new_list):
    with open('list.txt', 'w', encoding="utf-8") as f:
        f.write('\n'.join(new_list))
        f.close()


def apply_list(new_list, bring_list, keep_list):
    # bring
    bring_items = getAllItemsBring(bring_list)
    for item in bring_items:
        if item not in new_list:
            print('Deleting item from bring: ' + item)
            bring.removeItem(bring_list['listUuid'], item.encode('utf-8').decode('ISO-8859-9'))
    for item in new_list:
        if item not in bring_items:
            print('Adding item to bring: ' + item)
            bring.saveItem(bring_list['listUuid'], item.encode('utf-8').decode('ISO-8859-9'))

    # keep
    keep_items = getAllItemsKeep(keep_list)
    for item in keep_items:
        if item not in new_list:
            print('Deleting item from keep: ' + item)
            get_keep_list_item(item, keep_list).delete()
    for item in new_list:
        if item not in keep_items:
            print('Adding item to keep: ' + item)
            keep_list.add(item.encode('utf-8').decode('ISO-8859-9'), False, gkeepapi.node.NewListItemPlacementValue.Bottom)


def delete_duplicates(keep_list):
    items = getAllItemsKeep(keep_list)
    for item in items:
        if items.count(item) > 1:
            print('Deleting duplicate item: ' + item)
            get_keep_list_item(item, keep_list).delete()
            items.remove(item)


def get_keep_list_item(name, keep_list):
    for item in keep_list.unchecked:
        if item.text == name:
            return item
    return None


print('Starting app')
print('Sync mode: ' + str(SYNC_MODE))
print('Timeout: ' + str(TIMEOUT) + ' minutes')

login()

# load Keep
keep.sync()
keepList = keep.get(KEEP_LIST_ID)
delete_old_items(keepList)
delete_duplicates(keepList)
keep.sync()

# load Bring
bringList = get_bring_list(bring.loadLists()['lists'])

sync(keepList, bringList)

print('Starting scheduler')
schedule.every(TIMEOUT).minutes.do(sync, keepList, bringList)
while True:
    schedule.run_pending()
    time.sleep(1)
