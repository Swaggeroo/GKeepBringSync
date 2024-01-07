# Google Keep <-> Bring sync
This is a simple script to sync your Google Keep notes with Bring shopping lists and vice versa.

## Disclaimer
This script is not affiliated with Google or Bring. It is not guaranteed to work and may break at any time. Use at your own risk.
> It uses the unofficial [gkeepapi](https://pypi.org/project/gkeepapi/) and [bringapi](https://pypi.org/project/python-bring-api/) libraries.

## Installation
A sample Dockerfile is provided. You can also run it directly with Python (Only tested with 3.10 but should also work with 3.8+).

## Usage
You need to provide the following environment variables:
### Environment variables
| Variable          | Description                                                                                          | Default | Required |
|-------------------|------------------------------------------------------------------------------------------------------|---------|----------|
| `GOOGLE_EMAIL`    | Your Google account email address                                                                    |         | **Yes**  |
| `GOOGLE_PASSWORD` | Your Google account password - [App Password](https://myaccount.google.com/apppasswords) recommended |         | **Yes**  |
| `KEEP_LIST_ID`    | Your Google Note ID (visible in the URL when selecting a Note in the webapp)                         |         | **Yes**  |
| `BRING_EMAIL`     | Your Bring account email address                                                                     |         | **Yes**  |
| `BRING_PASSWORD`  | Your Bring account password                                                                          |         | **Yes**  |
| `SYNC_MODE`       | 0 = bidirectional, 1 = bring master, 2 = google master                                               | 0       | No       |
| `TIMEOUT`         | Timeout between syncs in *minutes*                                                                   | 60      | No       |
