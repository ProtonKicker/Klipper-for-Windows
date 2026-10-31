from .cli import main

if __name__ == "__main__":
    sys_exit = main()
    import sys
    sys.exit(sys_exit)
