# Google Keep <-> Bring sync
This is a simple script to sync your Google Keep notes with Bring shopping lists and vice versa. IMPORTANT: Read the whole readme, there are some special things to get it working.

## Disclaimer
This script is not affiliated with Google or Bring. It is not guaranteed to work and may break at any time. Use at your own risk.
> It uses the unofficial [gkeepapi](https://pypi.org/project/gkeepapi/) and [bringapi](https://pypi.org/project/python-bring-api/) libraries.

## Installation
A sample Dockerfile is provided. You can also run it directly with Python (Only tested with 3.10 but should also work with 3.8+).

## Usage
You need to provide the following environment variables:
### Environment variables
| Variable          | Description                                                                                                           | Default                      | Required |
|-------------------|-----------------------------------------------------------------------------------------------------------------------|------------------------------|----------|
| `GOOGLE_EMAIL`    | Your Google account email address                                                                                     |                              | **Yes**  |
| `GOOGLE_PASSWORD` | Your Google account password - [App Password](https://myaccount.google.com/apppasswords) recommended                  |                              | **Yes**  |
| `KEEP_LIST_ID`    | Your Google Note ID (visible in the URL when selecting a Note in the webapp)                                          |                              | **Yes**  |
| `BRING_EMAIL`     | Your Bring account email address                                                                                      |                              | **Yes**  |
| `BRING_PASSWORD`  | Your Bring account password                                                                                           |                              | **Yes**  |
| `SYNC_MODE`       | 0 = bidirectional, 1 = bring master, 2 = google master                                                                | 0                            | No       |
| `TIMEOUT`         | Timeout between syncs in *minutes* \| 0 = only run once (with the provided docker-compose it will restart infinitely) | 60                           | No       |
| `BRING_LIST_NAME` | Name of your Bring List                                                                                               | Using first list in Response | No       | 
| `GOOGLE_TOKEN`    | Overwrite Token logic with your own provided token                                                                    |                              | No       |

### Sync modes
| Mode | Description                                                                                           |
|------|-------------------------------------------------------------------------------------------------------|
| 0    | Bidirectional sync. Changes in Google Keep will be reflected in Bring and vice versa.                 |
| 1    | Bring master. Changes in Bring will be reflected in Google Keep. Google Keep changes will be ignored. |
| 2    | Google master. Changes in Google Keep will be reflected in Bring. Bring changes will be ignored.      |

### Please note
- **!!Important!!** I couldn't get the Google Auth work in the container. Therefore I first ran the script locally and copied the token.txt file to the container or used the GOOGLE_TOKEN env var. YES you need not matching dependencies (At least I needed). You probably need to install them manually. If you know how to fix this, please let me know.
- The token.txt file is used to store the Google Auth token. It is created automatically. You can delete it at any time to force a new login. Keep it safe as it can be used to access your Google account.
- I didn't test the expiration of the token yet. If it expires, the script will probably crash. At the next run it should delete the token.txt and crash again. After that it should work again. With docker this should be no problem as the container will be restarted automatically.
- At the first run the script will take the keep and bring lists and merge them (Only with SYNC_MODE 0). After that it will only sync changes.
- On my server it must run in host network mode.

## Helping hand(s)
[RealPotatoe](https://github.com/RealPotatoe) - Proofreading and general improvements
