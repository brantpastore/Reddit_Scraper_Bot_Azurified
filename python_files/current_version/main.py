from env_config import load_env_variables
from reddit_api import get_reddit_access_token
from discord_bot import ScraperBot

if __name__ == "__main__":
    env_vars = load_env_variables()

    print(env_vars)

    reddit_access_token = get_reddit_access_token(
        env_vars["REDDIT_CLIENT_ID"],
        env_vars["REDDIT_CLIENT_SECRET"],
        env_vars["REDDIT_USERNAME"],
        env_vars["REDDIT_PASSWORD"],
        env_vars["REDDIT_USER_AGENT"],
    )

    print(reddit_access_token)

    headers = {
        "Authorization": f"bearer {reddit_access_token}",
        "User-Agent": env_vars["REDDIT_USER_AGENT"],
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }

    print(headers)

    bot = ScraperBot(env_vars["DISCORD_TOKEN"], env_vars["WEBHOOK"], headers)
    bot.run()
