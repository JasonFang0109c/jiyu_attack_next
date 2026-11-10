"""源码与打包产物共用的应用入口。"""

import sys
from multiprocessing import freeze_support

from app.start.service import main

if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
