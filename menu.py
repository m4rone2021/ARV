# menu.py

def display_menu():
    """Prints the main menu options to the console."""
    print("\n" + "=" * 20)
    print("      MAIN MENU     ")
    print("=" * 20)
    print("1. Option One")
    print("2. Option Two")
    print("3. Exit")
    print("=" * 20)

def get_user_choice():
    """Prompts the user for input and returns their choice as a stripped string."""
    return input("Select an option (1-3): ").strip()
