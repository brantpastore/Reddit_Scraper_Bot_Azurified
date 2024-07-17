# Description:
# This file contains the main function that runs the
# bot in either CLI mode or Discord bot mode.
import time
import core_logic_reddit as core_logic
import logging
import sys
#import core_logic


def main():
    
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    
    # Create the bot object
    bot = core_logic.ScraperBot()

    # Run the bot
    bot.run_discord()
    
    # Ask the user for the mode they want to run the bot in 
    '''
    while True:
        mode = input(
            "Enter 'cli' for CLI mode or 'discord' for Discord bot mode: "
        ).lower()
        if mode == "cli":
            bot.run_cli()
            break
        elif mode == "discord":
            bot.run_discord()
            break
        elif mode == "exit":
            print("Exiting program.")
            time.sleep(1)
            break
        else:
             print("Invalid mode entered. Please try again.") 
    '''
    
main()