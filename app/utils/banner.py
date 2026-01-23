"""Green Deck ASCII art banner utility."""

import os

# ANSI color codes
GREEN = "\033[92m"
DARK_GREEN = "\033[32m"
LIGHT_GREEN = "\033[38;5;120m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def print_banner(clear_screen: bool = True) -> None:
    """Display the Green Deck ASCII art banner with colors.

    Args:
        clear_screen: Whether to clear the terminal before printing.
    """
    if clear_screen:
        os.system('cls' if os.name == 'nt' else 'clear')

    # Enable ANSI colors on Windows
    if os.name == 'nt':
        os.system('')

    banner = f"""
{LIGHT_GREEN}   _____ _____  ______ ______ _   _   {GREEN}  _____  ______ _____ _  __
{LIGHT_GREEN}  / ____|  __ \\|  ____|  ____| \\ | |  {GREEN} |  __ \\|  ____/ ____| |/ /
{LIGHT_GREEN} | |  __| |__) | |__  | |__  |  \\| |  {GREEN} | |  | | |__ | |    | ' /
{LIGHT_GREEN} | | |_ |  _  /|  __| |  __| | . ` |  {GREEN} | |  | |  __|| |    |  <
{LIGHT_GREEN} | |__| | | \\ \\| |____| |____| |\\  |  {GREEN} | |__| | |___| |____| . \\
{LIGHT_GREEN}  \\_____|_|  \\_\\______|______|_| \\_|  {GREEN} |_____/|______\\_____|_|\\_\\

{DARK_GREEN}             {YELLOW}AI-Powered Intelligent Flashcard Generator{DARK_GREEN}
{DARK_GREEN}                                                     
{DARK_GREEN}                                                      

{GREEN}  .:*~*:._.:*~*:._.:*~*:._.:*~*:._.:*~*:._.:*~*:._.:*~*:._.:*~*:.{RESET}
"""
    print(banner)
