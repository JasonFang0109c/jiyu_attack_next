"""允许通过 ``python -m app.gui`` 启动图形界面。"""

import sys

from app.start.gui import main

if __name__ == "__main__":
    sys.exit(main())
