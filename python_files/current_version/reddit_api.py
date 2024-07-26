import requests


def get_reddit_access_token(client_id, client_secret, username, password, user_agent):
    auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
    data = {
        "grant_type": "password",
        "username": username,
        "password": password,
    }
    headers = {"User-Agent": user_agent}

    response = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=auth,
        data=data,
        headers=headers,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise KeyError("Access token not found in response.")
    return token


def check_subreddit_exists(subreddit_name, headers):
    response = requests.get(
        f"https://oauth.reddit.com/r/{subreddit_name}/about", headers=headers
    )
    if response.status_code == 200:
        return True
    elif response.status_code == 404:
        return False
    else:
        response.raise_for_status()
