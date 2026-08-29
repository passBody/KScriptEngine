import sys

from widgets.main_widget import main


if __name__ == "__main__":
    path = None
    check = False
    for arg in sys.argv[1:]:
        if arg == "--check":
            check = True
        elif not path:
            path = arg
    sys.exit(main(path, check))
