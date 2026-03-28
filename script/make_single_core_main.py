import os
import json
from make_functions import *
    
def main():
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir('../Proba_ChampSim')
    
    for prefetcher in ['no', 'l2_sms_eviction', 'l2_bingo_eviction', 'l2_proba_bingo_eog_jail_sampling_1', 'l2_dspatch_eviction', 'l2_proba_eog_jail_sampling_1', 'l2_proba_eog_jail_sampling_1_calibration', 'l2_pmp_eviction', 'l2_proba_pmp_eog_jail_sampling_1', 'l2_proba_pmp_offset_pc_offset_eog_jail_sampling_1', 'l2_gaze_eviction']:
        make_1core_l2_prefetcher(prefetcher)
    
    print('Done.')


if __name__ == '__main__':
    main()
