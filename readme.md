# Google Keep <-> Bring sync
This is a simple script to sync your Google Keep notes with Bring shopping lists and vice versa. **IMPORTANT**: Read the whole readme, there are some special things to get it working.

## Disclaimer
This script is not affiliated with Google or Bring. It is not guaranteed to work and may break at any time. Use at your own risk.
> It uses the unofficial [gkeepapi](https://pypi.org/project/gkeepapi/) and [bring-api](https://pypi.org/project/bring-api/) libraries.

Bring catalog items are localized. The sync reads and writes catalog products in the language configured for the selected Bring list, rather than exposing Bring's canonical German IDs. This makes the sync suitable for English and other supported Bring list languages.

## Installation
A sample Dockerfile is provided. You can also run it directly with Python 3.11 or later.

## Usage
You need to provide the following environment variables:

### Acquire Master token
1. See https://gkeepapi.readthedocs.io/en/latest/#obtaining-a-master-token
2. And for oauth value: https://github.com/simon-weber/gpsoauth#alternative-flow 

Save the token in a file called `token.txt` in the same directory as the script or provide it as an environment variable `GOOGLE_TOKEN`

### Environment variables
| Variable          | Description                                                                                                           | Default                      | Required |
|-------------------|-----------------------------------------------------------------------------------------------------------------------|------------------------------|----------|
| `GOOGLE_EMAIL`    | Your Google account email address                                                                                     |                              | **Yes**  |
| `KEEP_LIST_ID`    | Your Google Note ID (visible in the URL when selecting a Note in the webapp)                                          |                              | **Yes**  |
| `BRING_EMAIL`     | Your Bring account email address                                                                                      |                              | **Yes**  |
| `BRING_PASSWORD`  | Your Bring account password                                                                                           |                              | **Yes**  |
| `SYNC_MODE`       | 0 = bidirectional, 1 = bring master, 2 = google master                                                                | 0                            | No       |
| `TIMEOUT`         | Timeout between syncs in *minutes* \| 0 = only run once (with the provided docker-compose it will restart infinitely) | 60                           | No       |
| `BRING_LIST_NAME` | Name of your Bring List                                                                                               | Using first list in Response | No       | 
| `BRING_LANGUAGE_CODE` | Bring article language for the selected list, for example `en-US`, `de-DE`, or `fr-FR`                            | `en-US`                      | No       |
| `GOOGLE_TOKEN`    | Master Token (See ### Acquire Master token)                                                                           |                              | No       |

### Sync modes
| Mode | Description                                                                                           |
|------|-------------------------------------------------------------------------------------------------------|
| 0    | Bidirectional sync. Changes in Google Keep will be reflected in Bring and vice versa.                 |
| 1    | Bring master. Changes in Bring will be reflected in Google Keep. Google Keep changes will be ignored. |
| 2    | Google master. Changes in Google Keep will be reflected in Bring. Bring changes will be ignored.      |

### Please note
- The token.txt file is used to store the Google Auth token. Keep it safe as it can be used to gain full access to your Google account.
- At the first run the script will take the keep and bring lists and merge them (Only with SYNC_MODE 0). After that it will only sync changes.
- At startup, the sync applies `BRING_LANGUAGE_CODE` to the selected Bring list and uses the same language when it reads and writes catalog items. Use a Bring-supported locale such as `en-US`.
- For me only host network works with the docker container.

## Helping hand(s)
[RealPotatoe](https://github.com/RealPotatoe) - Proofreading and general improvements
