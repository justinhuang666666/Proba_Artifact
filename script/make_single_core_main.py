import os
import json
from make_functions import *
    
def main():
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir('../../Proba_Champsim')
    
    for prefetcher in ['l2_sms','l2_sms_train_on_misstaghit','l2_proba_pc_offset','l2_proba_pcoffset_eog_jail_sampling','l2_proba_pc_pcoffset_offsetoffset_eog_jail_sampling','l2_superproba_pc_pcoffset_offsetoffset']:
        make_1core_l2_prefetcher(prefetcher)
    
    print('Done.')


if __name__ == '__main__':
    main()
