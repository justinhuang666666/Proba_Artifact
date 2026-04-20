import os
import json
from make_functions import *
    
def main():
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir('../../Proba_Champsim')
    
    for prefetcher in ['no', 'l2_sms', 'l2_bingo', 'l2_dspatch', 'l2_pmp', 'l2_gaze', 'l2_superproba']:
        make_1core_l2_prefetcher(prefetcher)
    
    print('Done.')


if __name__ == '__main__':
    main()
