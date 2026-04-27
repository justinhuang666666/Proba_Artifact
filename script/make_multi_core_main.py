import os
import json
from make_functions import *
    
def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    os.chdir('../../Proba_Champsim')
    for core in [2, 4, 8]:
        for prefetcher in ['l2_sms','l2_bingo','l2_dspatch','l2_pmp','l2_gaze','l2_superproba_pc_pcoffset_offsetoffset_80_80']:
            make_multicore(core, prefetcher)
    
    print('Done.')


if __name__ == '__main__':
    main()
