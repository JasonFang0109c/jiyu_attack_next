"""图形界面的包入口。"""

from multiprocessing import freeze_support
import sys

def main():
    from .gui.app import main as run_gui
    return run_gui()


if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
