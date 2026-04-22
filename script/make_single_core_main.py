import os
import json
from make_functions import *
    
def main():
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir('../../Proba_Champsim')
    
    for prefetcher in ['no', 'l2_sms', 'l2_bingo', 'l2_dspatch', 'l2_pmp', 'l2_gaze', 'l2_superproba_pc_pcoffset_offsetoffset_40_20', 'l2_superproba_pc_pcoffset_offsetoffset_40_40', 'l2_superproba_pc_pcoffset_offsetoffset_40_60', 'l2_superproba_pc_pcoffset_offsetoffset_40_80', 'l2_superproba_pc_pcoffset_offsetoffset_60_20', 'l2_superproba_pc_pcoffset_offsetoffset_60_40', 'l2_superproba_pc_pcoffset_offsetoffset_60_60', 'l2_superproba_pc_pcoffset_offsetoffset_60_80']:
        make_1core_l2_prefetcher(prefetcher)
    
    print('Done.')


if __name__ == '__main__':
    main()
