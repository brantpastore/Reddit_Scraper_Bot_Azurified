# Description:
# This file contains the core logic for the Reddit scraper bot.
# It uses Selenium to scrape posts from Reddit and sends the results to a Discord channel using webhooks.
# The bot can be run in the CLI or as a Discord bot.
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from urllib.parse import urlparse, urljoin
from azure.keyvault.secrets import SecretClient
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
import logging
import sys
import asyncio
import time
import requests
import re
import os
import discord
import logging
import undetected_chromedriver as uc
import asyncpraw
import aiohttp
import prawcore

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# check if being ran by a docker container
if os.getenv("CHECK_ENV"):
    # Running in a CLI or local environment

    # Load environment variables from a .env file
    load_dotenv()

    # Discord token and webhook URLs from local environment variables
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    WEBHOOK = os.getenv("WEBHOOK")

    print("DISCORD_TOKEN FROM CLI:", DISCORD_TOKEN)
    print("WEBHOOK FROM CLI:", WEBHOOK)

else:
    # Running in a web server environment (e.g., Azure App Service, Heroku)

    # Azure Key Vault URL
    vault_url = "https://FeashDiscordBot.vault.azure.net"

    # Create a secret client
    logger = logging.getLogger("azure.identity")
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter("[%(levelname)s %(name)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    credential = DefaultAzureCredential()  # ManagedIdentityCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)

    # Retrieve secrets from Azure Key Vault
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    WEBHOOK = os.getenv("WEBHOOK")

    print("DISCORD_TOKEN:", DISCORD_TOKEN)
    print("WEBHOOK:", WEBHOOK)

# Initialize Async PRAW
reddit = asyncpraw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent=os.getenv("REDDIT_USER_AGENT"),
)


# Function to sanitize the filename of the image or video scraped from Reddit
def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "_", filename)


class ScraperBot:
    post_urls = {}  # Dictionary to store post URLs

    def __init__(self):
        """original scraperbot code
        # set up selenium options for headless browsing
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )

        # service = Service(chromedriver_autoinstaller.install())
        # service = Service(ChromeDriverManager().install())
        # self.driver = webdriver.Chrome(service=service, options=options)

        # Initialize the undetected Chrome driver
        self.driver = uc.Chrome(options=options)
        """

        # Set up the Discord bot with specific intents
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.bot)

        # IMPORTANT: Change the subreddits to scrape here to whatever you want
        self.subreddits = {
            1: "memes",
            2: "combatfootage",
            3: "greentext",
            4: "dankmemes",
            5: "pics",
        }

        self.setup_bot_commands()

    def setup_bot_commands(self):

        @app_commands.describe(
            subreddit_number="The number of the subreddit to scrape",
            num_posts="The number of posts to scrape (default: 1)",
        )

        # Define the scrape command
        @self.tree.command(name="scrape", description="Scrape posts from a subreddit")
        async def scrape_command(
            interaction: discord.Interaction, subreddit_number: int, num_posts: int = 1
        ):
            if subreddit_number in self.subreddits:
                subreddit_url = self.subreddits[subreddit_number]

                await interaction.response.defer()

                await interaction.followup.send(
                    f"Starting to scrape {num_posts} posts from: {subreddit_url}"
                )

                await self.scrape_subreddit(interaction, subreddit_url, num_posts)

            else:
                await interaction.response.send_message(
                    "Invalid subreddit number. Please choose a number between 1 and 5."
                )

        # Define the list_subreddits command
        @self.tree.command(
            name="list_subreddits", description="List available subreddits"
        )
        async def list_subreddits(interaction: discord.Interaction):
            try:
                subreddit_list = "\n".join(
                    [f"{k}. {v}" for k, v in self.subreddits.items()]
                )
                await interaction.response.send_message(
                    f"Available subreddits to scrape:\n{subreddit_list}"
                )
            except Exception as e:
                print(f"Error listing subreddits: {e}")
                await interaction.response.send_message("Error listing subreddits.")

            # Define the scrape_custom command

        @self.tree.command(
            name="scrape_custom", description="Scrape posts from a custom subreddit"
        )
        async def scrape_custom_command(
            interaction: discord.Interaction, subreddit_name: str, num_posts: int = 1
        ):
            try:
                subreddit = await reddit.subreddit(
                    subreddit_name
                )  # Await the coroutine here
                subreddit_exists = subreddit.display_name

                if subreddit_exists:
                    await interaction.response.defer()
                    await interaction.followup.send(
                        f"Starting to scrape {num_posts} posts from: r/{subreddit_name}"
                    )
                    await self.scrape_subreddit(interaction, subreddit_name, num_posts)
                else:
                    await interaction.response.send_message(
                        "Invalid subreddit name. Community not found. Please provide a valid subreddit name."
                    )

            except Exception as e:
                await interaction.response.send_message(
                    f"An error occurred while processing the command: {str(e)}"
                )

    async def check_subreddit_exists(self, subreddit_name):
        try:
            subreddit = await reddit.subreddit(subreddit_name, fetch=True)
            return subreddit.display_name
        except:
            return None

    # Scrapes a subreddit and sends the results to the Discord channel
    async def scrape_subreddit(self, interaction, subreddit_url, num_posts):
        print(f"Scraping {num_posts} posts from: {subreddit_url}")
        try:
            subreddit = await reddit.subreddit(subreddit_url)  # Await the coroutine
            top_posts = subreddit.top(limit=num_posts)

            async for post in top_posts:
                await self.get_post_content(interaction, post)

        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}")
            print(f"An error occurred: {e}")

    # Get the content of a specific post
    async def get_post_content(self, post, interaction=None):
        print("Getting post content for", post.url)
        title = post.title
        image = post.url if post.url.endswith((".jpg", ".jpeg", ".png")) else None
        video = (
            post.media["reddit_video"]["fallback_url"]
            if post.media and "reddit_video" in post.media
            else None
        )

        if image and not video:  # If we found an image but no video, process the image
            await self.process_image(image, title, interaction)
        elif video and not image:  # If we found a video but no image, process the video
            await self.process_video(video, title, interaction)
        else:
            print("No image or video found.")

    # Process the image and send it to the Discord channel
    async def process_image(self, image_url, title, interaction=None):
        print("Image URL:", image_url)
        image_filename = sanitize_filename(f"{title}.png")

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                content = await response.read()

        with open(image_filename, "wb") as file:
            file.write(content)

        title_payload = {"content": title}
        files = {"file": open(image_filename, "rb")}

        await self.send_to_discord_channel(title_payload, files, interaction)

        files["file"].close()
        os.remove(image_filename)

    async def process_video(self, video_url, title, interaction=None):
        print("Video URL:", video_url)
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url, timeout=None) as response:
                extension = os.path.splitext(urlparse(video_url).path)[1] or ".mp4"
                video_filename = sanitize_filename(f"{title}{extension}")

                with open(video_filename, "wb") as video_file:
                    while True:
                        chunk = await response.content.read(1024)
                        if not chunk:
                            break
                        video_file.write(chunk)

        # Send video to Discord
        title_payload = {"content": title}
        files = {"file": open(video_filename, "rb")}

        await self.send_to_discord_channel(title_payload, files, interaction)

        files["file"].close()
        os.remove(video_filename)

    async def send_to_discord_channel(self, title_payload, files, interaction):
        # check the channel the command was called from,
        # and send the message to that channel
        text_channel = interaction.channel

        print(f"Sending message to channel: {text_channel}")

        # send the message with the title payload
        await text_channel.send(content=title_payload["content"])

        # send the files if there are any
        if files:
            for key, value in files.items():
                await text_channel.send(file=discord.File(value))
                files[key].close()

        return

    # Get the subreddit from the user in the CLI
    def getSubredditCLI(self):
        print("Which subreddit would you like to scrape?")
        for key, value in self.subreddits.items():
            print(f"{key}. {value}")
        while True:
            subreddit = int(
                input("Enter the number of the subreddit you would like to scrape: ")
            )
            if subreddit in self.subreddits:
                return self.subreddits[subreddit]
            else:
                print("Invalid input. Please enter a valid choice.")

    # Select the number of posts to scrape from the subreddit
    async def select_posts(self, subreddit_name, num_posts):
        try:
            subreddit = await reddit.subreddit(subreddit_name)
            top_posts = subreddit.top(limit=num_posts)
            return [post async for post in top_posts]
        except prawcore.exceptions.NotFound:
            print(f"Subreddit {subreddit_name} not found.")
            return []
        except prawcore.exceptions.RequestException as e:
            print(f"RequestException: {e}")
            return []
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return []

    # Run the CLI interface
    def run_cli(self):
        subreddit_name = self.getSubredditCLI()
        num_posts = int(input("How many posts would you like to scrape? "))

        # Define an async function to run the CLI
        async def cli_helper():
            top_posts = await self.select_posts(subreddit_name, num_posts)
            if not top_posts:
                print(f"No posts found for subreddit: {subreddit_name}")
                return
            for post in top_posts:
                await self.get_post_content(post)

        # Get the existing event loop or create a new one if none exists
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(cli_helper())
                new_loop.close()
            else:
                loop.run_until_complete(cli_helper())
        except Exception as e:
            print(f"An error occurred: {e}")

    # async commands
    async def sync_commands(self):
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

    # Run the Discord bot
    def run_discord(self):
        # Define the on_ready event
        @self.bot.event
        async def on_ready():
            await self.sync_commands()
            print(f"{self.bot.user} has connected to Discord!")
            print(f"Bot is active in {len(self.bot.guilds)} servers.")
            print("Ready to receive commands!")

            # Send a call to the webhook that the bot is ready
            try:
                webhook_message = {
                    "content": f"{self.bot.user} is ready to receive commands!"
                }
                requests.post(WEBHOOK, json=webhook_message)
            except Exception as e:
                print(f"Failed to send webhook message: {e}")

        self.bot.run(DISCORD_TOKEN)
