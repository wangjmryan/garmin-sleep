import os
import requests

TOKEN_URL = "https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token"


def get_token():
    """Swap the API key (from GARMIN_API_KEY) for a 24-hour bearer token."""
    api_key = os.environ.get("GARMIN_API_KEY")
    if api_key is None:
        raise SystemExit("GARMIN_API_KEY isn't set")

    headers = {"Accept": "*/*", "Authorization": f"ApiKey {api_key.strip()}"}
    response = requests.post(TOKEN_URL, headers=headers)

    if response.status_code != 200:
        raise SystemExit(f"Token request failed ({response.status_code}): {response.text}")

    # Garmin sends the token back as plain text (not JSON)
    return response.text.strip()


# This part only runs when you do `python get_token.py`,
# not when another file does `from get_token import get_token`
if __name__ == "__main__":
    token = get_token()
    print(f"Success! Got a token ({len(token)} characters).")
