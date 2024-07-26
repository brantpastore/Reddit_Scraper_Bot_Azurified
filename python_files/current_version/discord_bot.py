import discord
import requests
from discord import app_commands
from discord.ext import commands
from reddit_api import check_subreddit_exists
from web_scraper import WebScraper

# Constants for dropdown menu options
FILTER_TYPES = ["hot", "new", "top", "rising"]
TIME_RANGES = ["hour", "day", "week", "month", "year", "all"]
NUM_POSTS = [1, 2, 3, 4, 5]


class ScraperBot:
    def __init__(self, token, webhook, reddit_headers):
        self.token = token
        self.webhook = webhook
        self.reddit_headers = reddit_headers
        self.bot = discord.Client(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self.bot)
        self.subreddits = {
            1: "memes",
            2: "combatfootage",
            3: "greentext",
            4: "dankmemes",
            5: "pics",
        }
        self.scraper = WebScraper(self.reddit_headers)
        self.setup_bot_commands()

    def setup_bot_commands(self):
        @self.tree.command(name="scrape", description="Scrape posts from a subreddit")
        async def scrape_command(
            interaction: discord.Interaction,
            subreddit_number: int,
            num_posts: int = 1,
            filter_type: str = "hot",
            time_range: str = None,
        ):
            if subreddit_number in self.subreddits:
                subreddit_url = self.subreddits[subreddit_number]

                if num_posts > 5:
                    num_posts = 5
                elif num_posts < 1:
                    num_posts = 1

                await interaction.response.defer()
                await interaction.followup.send(
                    f"Starting to scrape {num_posts} posts from: r/{subreddit_url}"
                )
                await self.scraper.scrape_subreddit(
                    interaction, subreddit_url, num_posts, filter_type, time_range
                )
            else:
                await interaction.response.send_message(
                    "Invalid subreddit number. Please choose a number between 1 and 5."
                )

        @self.tree.command(
            name="list_subreddits", description="List available subreddits"
        )
        async def list_subreddits(interaction: discord.Interaction):
            subreddit_list = "\n".join(
                [f"{k}. {v}" for k, v in self.subreddits.items()]
            )
            await interaction.response.send_message(
                f"Available subreddits to scrape:\n{subreddit_list}"
            )

        @self.tree.command(
            name="scrape_custom", description="Scrape posts from a custom subreddit"
        )
        async def scrape_custom_command(
            interaction: discord.Interaction,
            subreddit_name: str,
            num_posts: int = 1,
            filter_type: str = "hot",
            time_range: str = None,
        ):
            subreddit_exists = check_subreddit_exists(
                subreddit_name, self.reddit_headers
            )
            if subreddit_exists:

                if num_posts > 5:
                    num_posts = 5
                elif num_posts < 1:
                    num_posts = 1

                await interaction.response.defer()
                await interaction.followup.send(
                    f"Starting to scrape {num_posts} posts from: r/{subreddit_name}"
                )
                await self.scraper.scrape_subreddit(
                    interaction, subreddit_name, num_posts, filter_type, time_range
                )
            else:
                await interaction.response.send_message(
                    "Invalid subreddit name. Community not found. Please provide a valid subreddit name."
                )

        @scrape_custom_command.autocomplete("filter_type")
        async def filter_type_autocomplete(
            interaction: discord.Interaction, current: str
        ):
            return [
                app_commands.Choice(name=ft, value=ft)
                for ft in FILTER_TYPES
                if current.lower() in ft.lower()
            ]

        @scrape_custom_command.autocomplete("time_range")
        async def time_range_autocomplete(
            interaction: discord.Interaction, current: str
        ):
            return [
                app_commands.Choice(name=tr, value=tr)
                for tr in TIME_RANGES
                if current.lower() in tr.lower()
            ]

        @scrape_custom_command.autocomplete("num_posts")
        async def num_posts_autocomplete(
            interaction: discord.Interaction, current: str
        ):
            return [
                app_commands.Choice(name=str(n), value=n)
                for n in NUM_POSTS
                if current in str(n)
            ]

        @scrape_command.autocomplete("subreddit_number")
        async def subreddit_number_autocomplete(
            interaction: discord.Interaction, current: str
        ):
            return [
                app_commands.Choice(name=str(k), value=k)
                for k in self.subreddits.keys()
                if current in str(k)
            ]

        @scrape_command.autocomplete("filter_type")
        async def filter_type_autocomplete(
            interaction: discord.Interaction, current: str
        ):
            return [
                app_commands.Choice(name=ft, value=ft)
                for ft in FILTER_TYPES
                if current.lower() in ft.lower()
            ]

        @scrape_command.autocomplete("time_range")
        async def time_range_autocomplete(
            interaction: discord.Interaction, current: str
        ):
            return [
                app_commands.Choice(name=tr, value=tr)
                for tr in TIME_RANGES
                if current.lower() in tr.lower()
            ]

        @scrape_command.autocomplete("num_posts")
        async def num_posts_autocomplete(
            interaction: discord.Interaction, current: str
        ):
            return [
                app_commands.Choice(name=str(n), value=n)
                for n in NUM_POSTS
                if current in str(n)
            ]

    # async commands
    async def sync_commands(self):
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

    """ # async guild commands
    async def sync_commands(self):
        try:
            # Specify a guild ID for faster syncing during development
            guild = discord.Object(id="730835327908053152")
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} command(s) in the guild.")
        except Exception as e:
            print(f"Failed to sync commands: {e}")"""

    def run(self):
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
                requests.post(self.webhook, json=webhook_message)
            except Exception as e:
                print(f"Error sending message to webhook: {e}")

        self.bot.run(self.token)
