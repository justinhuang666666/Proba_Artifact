import os
import json
from make_functions import *
    
def main():
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir('../../Proba_Champsim')
    
    for prefetcher in ['no', 'l2_sms_eviction', 'l2_bingo_eviction', 'l2_dspatch_eviction', 'l2_pmp_eviction', 'l2_gaze_eviction', 'l2_superproba']:
        make_1core_l2_prefetcher(prefetcher)
    
    print('Done.')


if __name__ == '__main__':
    main()
