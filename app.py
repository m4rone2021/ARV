# app.py
from menu import display_menu, get_user_choice

def main():
    while True:
        display_menu()
        choice = get_user_choice()

        if choice == "1":
            print("\nExecuting Option 1...")
        elif choice == "2":
            print("\nExecuting Option 2...")
        elif choice == "3":
            print("\nExiting application. Goodbye!")
            break
        else:
            print("\nInvalid choice. Please try again.")

if __name__ == "__main__":
    main()
