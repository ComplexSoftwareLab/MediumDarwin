#!/usr/bin/env python3
import sys
import time
import datetime
from mediumdarwin.Schemata import parseCmdArgs
from optparse import OptionParser


def main(args):
    s_time = time.time()
    optionParser = OptionParser()
    options, filterType, filterList, higherOrder = parseCmdArgs(
        optionParser, args
    )
    if (options.reset):
        from mediumdarwin.Schemata import Schemata
        schemata = Schemata()
        schemata.cleanup_mediumDarwin()
    else:
        from mediumdarwin.Schemata import Schemata
        schemata = Schemata()
        try:
            if options.isSchemataActive:
                schemata.main()
            elif options.isCoverageActive:
                from mediumdarwin.MediumDarwin import MediumDarwin
                littleDarwin = MediumDarwin()
                littleDarwin.main()
            else:
                from mediumdarwin.original import LittleDarwin as LittleDarwin_original
                LittleDarwin_original.main()
        finally:
            schemata.cleanup_mediumDarwin()

    print("elapsed: " + str(datetime.timedelta(seconds=int(time.time() - s_time))))
    return 0


if __name__ == "__main__":
    main(sys.argv)
