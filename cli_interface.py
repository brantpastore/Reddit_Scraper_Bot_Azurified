# Description:
# This file contains the main function that runs the
# bot in either CLI mode or Discord bot mode.
import time
import core_logic


def main():
    # Create the bot object
    bot = core_logic.ScraperBot()

    # Ask the user for the mode they want to run the bot in
    bot.run_discord()



main()
