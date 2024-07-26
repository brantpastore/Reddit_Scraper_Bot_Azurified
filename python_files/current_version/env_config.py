from dotenv import load_dotenv
import os
import logging
import sys
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential


def load_env_variables():
    if os.getenv("CHECK_ENV"):
        load_dotenv()
        return {
            "REDDIT_CLIENT_ID": os.getenv("REDDIT_CLIENT_ID"),
            "REDDIT_CLIENT_SECRET": os.getenv("REDDIT_CLIENT_SECRET"),
            "REDDIT_USER_AGENT": os.getenv("REDDIT_USER_AGENT"),
            "REDDIT_USERNAME": os.getenv("REDDIT_USERNAME"),
            "REDDIT_PASSWORD": os.getenv("REDDIT_PASSWORD"),
            "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN"),
            "WEBHOOK": os.getenv("WEBHOOK"),
        }
    else:
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
        logger = logging.getLogger(__name__)
        vault_url = "https://FeashDiscordBot.vault.azure.net"
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)
        return {
            "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN"),
            "WEBHOOK": os.getenv("WEBHOOK"),
            "REDDIT_CLIENT_ID": os.getenv("REDDIT_CLIENT_ID"),
            "REDDIT_CLIENT_SECRET": os.getenv("REDDIT_CLIENT_SECRET"),
            "REDDIT_USER_AGENT": os.getenv("REDDIT_USER_AGENT"),
            "REDDIT_USERNAME": os.getenv("REDDIT_USERNAME"),
            "REDDIT_PASSWORD": os.getenv("REDDIT_PASSWORD"),
        }
