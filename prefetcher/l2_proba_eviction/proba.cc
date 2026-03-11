#include "proba.h"
#include "cache.h"

#include <assert.h>

/*
 * Proba: Spatial Memory Streaming with Probabilistic Updates
 *
 * To appear in 
 *
 * @Authors: Yinting Huang, Jacky Wong, Sam Ainsworth
 * @Manteiners: Yinting Huang
 * @Email: yinting_justin_huang@outlook.com
 * @Date: 01/03/2026
 */

static std::vector<proba::Proba> prefetchers;

namespace proba {

// ------------------------- AGT functions ------------------------- //
ActiveGenerationTable::ActiveGenerationTable(int size, int num_ways) :
    Super(size, num_ways) {}

ActiveGenerationTable::Entry* ActiveGenerationTable::set_pattern(uint64_t region_num, uint64_t offset) {
    uint64_t key = build_key(region_num);
    Entry* entry = Super::find(key);
    if (!entry)
        return nullptr;
    else {
        entry->data.pattern[offset] = true;
        Super::rp_promote(key);
        return entry;
    }
}

ActiveGenerationTable::Entry ActiveGenerationTable::insert(uint64_t region_num, uint64_t trigger_offset, uint64_t pc) {
    uint64_t key = build_key(region_num);
    std::vector<bool> pattern(NUM_BLOCKS, false);
    pattern[trigger_offset] = true;
    Entry old_entry = Super::insert(key, {trigger_offset, pc, pattern});
    Super::rp_insert(key);
    return old_entry;
}

int ActiveGenerationTable::get_num_valid_entries_per_set(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    return Super::get_num_valid_entries_per_set(key);
}


ActiveGenerationTable::Entry* ActiveGenerationTable::erase(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    return Super::erase(key);
}

std::string ActiveGenerationTable::log() {
    std::vector<std::string> headers({"RegionNum", "Trigger Offset", "PC", "Pattern"});
    return Super::log(headers);
}

void ActiveGenerationTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    table.set_cell(row, 0, entry.key);
    table.set_cell(row, 1, entry.data.trigger_offset);
    table.set_cell(row, 2, entry.data.pc);
    table.set_cell(row, 3, custom_util::pattern_to_string(entry.data.pattern));
}

uint64_t ActiveGenerationTable::build_key(uint64_t region_num) {
    uint64_t key = region_num & ((1ULL << 37) - 1);
    return key;
}


// ------------------------- PHT functions ------------------------- //
PatternHistoryTable::PatternHistoryTable(int size, int num_ways) :
    Super(size, num_ways) {
    std::cout << "Pattern Table index_len: " << Super::index_len << std::endl;
}

void PatternHistoryTable::insert(uint64_t pc, const std::vector<int> &pattern) {
    assert((int)pattern.size() == proba::NUM_BLOCKS);
    uint64_t key = build_key(pc);
    // std::cout<<"pc key: "<<std::hex<<key<<std::dec<<std::endl;
    custom_util::SaturatingCounter mode(3,4);
    Super::insert(key, {pattern, mode});
    Super::rp_insert(key);  
}

void PatternHistoryTable::update(uint64_t pc, const std::vector<int> &pattern, const custom_util::SaturatingCounter &mode) {
    assert((int)pattern.size() == proba::NUM_BLOCKS);
    uint64_t key = build_key(pc);
    // std::cout<<"pc key: "<<std::hex<<key<<std::dec<<std::endl;
    Super::update(key, {pattern, mode});
    Super::rp_promote(key);  
}

PatternHistoryTable::Entry* PatternHistoryTable::find(uint64_t pc) {
    uint64_t key = build_key(pc);
    // std::cout<<"pc key: "<<std::hex<<key<<std::dec<<std::endl;
    return Super::find(key);
}

std::string PatternHistoryTable::log() {
    std::vector<std::string> headers({"Key", "Pattern", "Mode"});
    return Super::log(headers);
}

void PatternHistoryTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    table.set_cell(row, 0, entry.key);
    table.set_cell(row, 1, custom_util::pattern_to_string(entry.data.pattern));
    table.set_cell(row, 2, static_cast<int>(entry.data.mode.get_cnt()));
}

uint64_t PatternHistoryTable::build_key(uint64_t pc) {
    return custom_util::hash_index(pc, this->index_len);
}

// ------------------------- PB functions ------------------------- //
PrefetchBuffer::PrefetchBuffer(int size, int pattern_len, int debug_level = 0, int num_ways = 8) :
    Super(size, num_ways), pattern_len(pattern_len), debug_level(debug_level) {
        if (this->debug_level >= 1)
            std::cerr << "PrefetchBuffer::PrefetchBuffer(size=" << size << ", pattern_len=" << pattern_len
                      << ", debug_level=" << debug_level << ", num_ways=" << num_ways << ")" << std::dec << std::endl;
}

void PrefetchBuffer::insert(uint64_t region_num, std::vector<int> pattern) {
    if (this->debug_level >= 2)
        std::cerr << "PrefetchBuffer::insert(region_number=0x" << std::hex << region_num
                    << ", pattern=" << custom_util::pattern_to_string(pattern) << ")" << std::dec << std::endl;
    uint64_t key = this->build_key(region_num);
    Super::insert(key, {pattern});
    Super::rp_insert(key);
}

int PrefetchBuffer::prefetch(CACHE* cache, uint64_t block_num) {
    uint64_t base_addr = block_num << LOG2_BLOCK_SIZE;
    int region_offset = block_num % this->pattern_len;
    uint64_t region_number = block_num / this->pattern_len;
    uint64_t key = this->build_key(region_number);
    Entry* entry = Super::find(key);
    if (!entry) {
        return 0;
    }
    Super::set_mru(key);
    int pf_issued = 0;
    std::vector<int>& pattern = entry->data.pattern;
    pattern[region_offset] = 0; /* accessed block will be automatically fetched if necessary (miss) */
    int pf_offset;
    /* prefetch blocks that are close to the recent access first (locality!) */
    for (int d = 1; d < this->pattern_len; d += 1) {
        /* prefer positive strides */
        for (int sgn = +1; sgn >= -1; sgn -= 2) {
            pf_offset = region_offset + sgn * d;
            if (0 <= pf_offset && pf_offset < this->pattern_len && pattern[pf_offset] > 0) {
                uint64_t pf_address = (region_number * this->pattern_len + pf_offset) << LOG2_BLOCK_SIZE;
                if (cache->get_occupancy(3, 0) + cache->get_occupancy(0, 0) < cache->get_size(0, 0) - 1 && cache->get_occupancy(3, 0) < cache->get_size(3, 0)) {
                    uint32_t pf_metadata = 0;
                    pf_metadata = __add_pf_sour_level(pf_metadata, 2);
                    pf_metadata = __add_pf_dest_level(pf_metadata, 2);
                    int ok = cache->prefetch_line(0, base_addr, pf_address, true, pf_metadata);
                    // assert(ok == 1);
                    pf_issued += 1;
                    pattern[pf_offset] = 0;
                } else {
                    /* prefetching limit is reached */
                    return pf_issued;
                }
            }
        }
    }
    Super::erase(key);
    return pf_issued;
}

std::string PrefetchBuffer::log() {
    std::vector<std::string> headers({"Region", "Pattern"});
    return Super::log(headers);
}

void PrefetchBuffer::write_data(Entry& entry, custom_util::Table& table, int row) {
    table.set_cell(row, 0, entry.key);
    table.set_cell(row, 1, custom_util::pattern_to_string(entry.data.pattern));
}

uint64_t PrefetchBuffer::build_key(uint64_t region_num) {
    return custom_util::hash_index(region_num, this->index_len);
}

// ------------------------- Proba functions ------------------------- //

Proba::Proba(int agt_size, int agt_ways, int pht_size, int pht_ways, int jt_size, int pb_size, int pb_ways, bool is_debug, int cpu = 0) :
    agt(agt_size, agt_ways), pht(pht_size, pht_ways), jt(jt_size), pb(pb_size, NUM_BLOCKS), is_debug(is_debug), cpu(cpu) {
}

void Proba::ewma_update(uint64_t& ewma, uint64_t sample, int alpha_num, int alpha_den)
{
    // new = (1-α)*old + α*sample  (with rounding)
    uint64_t acc = (alpha_den - alpha_num) * ewma + alpha_num * sample;

    ewma = static_cast<uint64_t>(acc / alpha_den);
}

std::pair<uint64_t,uint64_t> Proba::get_probs(custom_util::SaturatingCounter mode) {
    assert(!(mode.get_cnt() < 0 || mode.get_cnt() > 7));

    static constexpr std::array<uint64_t,8> insert_probabilities = {
        1, 5, 10, 40, 100, 100, 100, 100
    };
    static constexpr std::array<uint64_t,8> delete_probabilities = {
        100, 100, 100, 100, 100, 60, 40, 20
    };
    return { insert_probabilities[mode.get_cnt()], delete_probabilities[mode.get_cnt()] };
}

void Proba::access(uint64_t block_num, uint64_t pc, CACHE* cache) {
    uint64_t region_num = block_num >> (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE);
    uint64_t region_offset = __region_offset(block_num);
    auto agt_entry = this->agt.set_pattern(region_num, region_offset);
    if (agt_entry) {
        if (is_debug) {
            std::cout << "Matching AGT entry, appending offset" <<std::endl;
            std::cout << "pc: 0x" <<std::hex << pc << ", addr: 0x" << block_num << ", region: 0x" << region_num << ", offset: " << std::dec << region_offset << std::endl;
        }
        return;
    } else {
        if(!this->jt.in_jail(region_num)||!use_jail_table) {
            if (is_debug) {
                std::cout << "Trigger access" <<std::endl;
                std::cout << "pc: 0x" <<std::hex << pc << ", addr: 0x" << block_num << ", region: 0x" << region_num << ", offset: " << std::dec << region_offset << std::endl;
            }
            
            auto pht_entry = pht.find(pc);
            // TODO: update replacement?
            if(pht_entry){
                if (is_debug) std::cout << "Original prefetch pattern:  " <<custom_util::pattern_to_string(pht_entry->data.pattern)<< std::endl;
                pb.insert(region_num, rotate(pht_entry->data.pattern, region_offset));
                if (is_debug) std::cout << "Rotated prefetch pattern:   " <<custom_util::pattern_to_string(rotate(pht_entry->data.pattern, region_offset))<< std::endl;
            }

            int num_valid_entries = agt.get_num_valid_entries_per_set(region_num);

            bool sample = false;

            if(num_valid_entries<=(AGT_WAY/2)){
                if (is_debug) std::cout << "AGT occupancy smaller than 50 percent, no sampling" <<std::endl;
                sample=true;
            } else {
                if (is_debug) std::cout << "AGT occupancy greater than 50 percent, sampling" <<std::endl;
                if(random_gen() < sample_rate){
                    sample=true;
                    if (is_debug) std::cout << "Region is sampled" <<std::endl;
                } else {
                    if (is_debug) std::cout << "Region is not sampled" <<std::endl;
                }
            }

            if(!use_sampling||sample){
                auto agt_victim = agt.insert(region_num, region_offset, pc);

                if (is_debug) {
                    std::cout << "AGT inserting region 0x" << std::hex << region_num << "pc: 0x" << pc << std::dec << ", offset: " << region_offset << std::endl;
                    std::cout << agt.log() << std::endl;
                }

                if (agt_victim.valid) {
                    update_in_pht(agt_victim, false, cache);
                }
            } else {
                jt.mark(region_num);
                if (is_debug) std::cout << "Mark region 0x" << std::hex << region_num << std::dec << " in Jail Table" << std::endl;
            }
        }
    }
    return;
}

void Proba::eviction(uint64_t block_num, CACHE* cache) {
    if (is_debug) std::cout << "Eviction" <<std::endl;
    uint64_t region_num = block_num >> (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE);
    auto entry = agt.erase(region_num);
    
    if (entry) {
        update_in_pht(*entry, true, cache);
        if (is_debug) {
            std::cout << "In AGT, AGT erasing region: 0x" << std::hex << region_num << std::dec <<std::endl;
            std::cout << "PHT updating pc: 0x" << std::hex << entry->data.pc << std::dec << "\n" << pht.log() << std::endl;
        }
    } else {
        jt.unmark(region_num);
        if (is_debug) {
            std::cout << "Not in AGT, unmark region 0x" << std::hex << region_num << std::dec << " in Jail Table" << std::endl;
        }
    }
}

int Proba::prefetch(CACHE* cache, uint64_t block_num) {
    return pb.prefetch(cache, block_num);
}

void Proba::log() {
    std::cout << "Accumulation table begin" << std::dec << std::endl;
    std::cout << this->agt.log();
    std::cout << "Accumulation table end" << std::endl;

    std::cout << "Pattern table begin" << std::dec << std::endl;
    std::cout << this->pht.log();
    std::cout << "Pattern table end" << std::endl;

    std::cout << "Prefetch buffer begin" << std::dec << std::endl;
    std::cout << this->pb.log();
    std::cout << "Prefetch buffer end" << std::endl;
}

void Proba::update_in_pht(const ActiveGenerationTable::Entry& agt_entry, bool is_end_of_generation, CACHE* cache) {
    if(is_end_of_generation){
        if (is_debug) std::cout << "AGT end-of-generation eviction" << std::endl;
    } else {
        jt.mark(agt_entry.key);
        if (is_debug) std::cout << "AGT capacity eviction, mark region 0x" <<std::hex<<agt_entry.key<<std::dec<< std::endl;
    }

    if(!use_only_training_on_eog || is_end_of_generation){
        auto pht_entry = pht.find(agt_entry.data.pc);
        if(pht_entry){
            if (is_debug) std::cout << "PHT entry found" << std::endl;
            const std::vector<int> &observation = rotate(pattern_bool2int(agt_entry.data.pattern), -agt_entry.data.trigger_offset);
            std::vector<int> prediction = pht_entry->data.pattern;
            custom_util::SaturatingCounter mode = pht_entry->data.mode;

            if (is_debug) {
                std::cout << "PC Tag:             " << agt_entry.data.pc <<std::endl;
                std::cout << "Observation:        " << custom_util::pattern_to_string(observation)<< std::endl;
                std::cout << "Prediction:         " << custom_util::pattern_to_string(pht_entry->data.pattern) <<std::endl;
            }

            uint64_t pop_count_observation             = count_bits_set(observation) - 1;
            uint64_t pop_count_prediction              = count_bits_set(prediction) - 1;
            uint64_t same_count_observation_prediction = count_bits_same(prediction, observation) - 1;

            if (is_debug) {
                std::cout << "same_count_observation_prediction: " << std::dec << same_count_observation_prediction <<std::endl;
                std::cout << "pop_count_prediction:              " << std::dec << pop_count_prediction << std::endl;
            }

            // EWMA
            if (num_valid_update == ewma_window_size) {
                uint64_t window_accuracy_estimate = 0;

                if (global_pf_sum > 0) {
                    window_accuracy_estimate =
                        (100ULL * static_cast<uint64_t>(global_accurate_pf_sum)) /
                        static_cast<uint64_t>(global_pf_sum);
                }

                uint64_t cur_pf_useful = static_cast<uint64_t>(cache->sim_stats.pf_useful);
                uint64_t cur_pf_unused = static_cast<uint64_t>(cache->sim_stats.pf_useless);

                uint64_t window_pf_useful = 0;
                uint64_t window_pf_unused = 0;

                if ((cur_pf_useful >= prev_pf_useful) && (cur_pf_unused >= prev_pf_unused)) {
                    window_pf_useful = cur_pf_useful - prev_pf_useful;
                    window_pf_unused = cur_pf_unused - prev_pf_unused;
                }

                uint64_t window_global_accuracy = 0;
                if (window_pf_useful + window_pf_unused > 0) {
                    window_global_accuracy =
                        (100ULL * window_pf_useful) /
                        (window_pf_useful + window_pf_unused);
                }

                if (total_num_valid_update == ewma_window_size) {
                    ewma_accuracy_estimate = window_accuracy_estimate;
                    ewma_global_accuracy   = window_global_accuracy;
                } else {
                    if((cur_pf_useful >= prev_pf_useful)&&(cur_pf_unused >= prev_pf_unused)) {
                        ewma_update(ewma_accuracy_estimate, window_accuracy_estimate, ewma_alpha_num, ewma_alpha_den);
                        ewma_update(ewma_global_accuracy, window_global_accuracy, ewma_alpha_num, ewma_alpha_den);
                    }
                }

                global_accurate_pf_sum = 0;
                global_pf_sum = 0;

                prev_pf_useful = cur_pf_useful;
                prev_pf_unused = cur_pf_unused;

                num_valid_update = 0;
            } else {
                global_accurate_pf_sum += same_count_observation_prediction;
                global_pf_sum += pop_count_prediction;

                num_valid_update++;
            }

            uint64_t local_accuracy = 0;
            {
                double tmp = 0.0;
                if (pop_count_prediction > 0) {
                    tmp = (static_cast<double>(same_count_observation_prediction) /
                        static_cast<double>(pop_count_prediction)) * 100.0;
                }
                local_accuracy = static_cast<uint64_t>(tmp);
            }

            uint64_t estimated_global_accuracy = ewma_accuracy_estimate;

            uint64_t local_acc_thr       = proba_acc_thr;
            uint64_t corrected_accuracy  = local_accuracy;

            if (is_accuracy_targeter&&(ewma_global_accuracy!=0)) {
                uint64_t act = ewma_global_accuracy;
                uint64_t thr = proba_acc_thr;
                local_acc_thr = 2*thr - act;
            }

            if (is_accuracy_correction) {
                uint64_t loc = local_accuracy;
                uint64_t act = ewma_global_accuracy;
                uint64_t est = estimated_global_accuracy;
                corrected_accuracy = loc + (act - est);
            }

            corrected_accuracy = std::clamp<uint64_t>(corrected_accuracy, 0, 100);
            local_acc_thr      = std::clamp<uint64_t>(local_acc_thr, 0, 100);

            if (is_debug) {
                std::cout << "Local Accuracy:            " << std::dec << local_accuracy <<std::endl;
                std::cout << "Actual Global Accuracy:    " << std::dec << ewma_global_accuracy <<std::endl;
                std::cout << "Estimated Global Accuracy: " << std::dec << estimated_global_accuracy <<std::endl;
                std::cout << "Corrected Accuracy:        " << std::dec << corrected_accuracy <<std::endl;
            }

            if(pop_count_prediction > 0){
                if(corrected_accuracy > local_acc_thr) {
                    mode.inc();
                    if (is_debug) std::cout << "Accuracy greater than threshold, increment mode: " << mode.get_cnt() <<std::endl;
                } else {
                    mode.dec();
                    if (is_debug) std::cout << "Accuracy less than threshold, decrement mode: " << mode.get_cnt() <<std::endl;
                }
            }

            std::pair<uint64_t,uint64_t> probs = get_probs(mode);

            uint64_t insert_probability = probs.first;
            uint64_t delete_probability = probs.second;

            if (is_debug) {
                std::cout << "insert probability: " << std::dec << insert_probability <<std::endl;
                std::cout << "delete probability: " << std::dec << delete_probability << std::endl;
            }

            for (int i = 0; i < NUM_BLOCKS; ++i) {
                double rand = random_gen();
                if (prediction[i]&&!observation[i]) {
                    // If the address is in prediction but not found in new observation
                    // Delete with a chance based on delete_probability
                    if (rand < delete_probability) {
                        prediction[i] = 0;
                    }
                } else if (!prediction[i]&&observation[i]){
                    // If the address is in new observation but not found in prediction
                    // Insert with a chance based on insert_probability
                    if (rand < insert_probability) {
                        prediction[i] = PF_FILL_L2;
                    }
                }
            }

            if (is_debug) {
                std::cout << "Updated Prediction: " << custom_util::pattern_to_string(prediction) <<std::endl;
            }

            pht.update(agt_entry.data.pc, prediction, mode);
        } else {
            if(count_bits_set(pattern_bool2int(agt_entry.data.pattern))>1){
                if (is_debug) std::cout << "PHT entry not fount, insert new PHT entry" <<std::endl;
                pht.insert(agt_entry.data.pc, rotate(pattern_bool2int(agt_entry.data.pattern), -agt_entry.data.trigger_offset));
            }
        }
    }

}

void Proba::set_warmup(bool warmup) {
    this->warmup = warmup;
    this->pb.warmup = warmup;
}

// ------------------------- util functions ------------------------- //
std::vector<int> pattern_bool2int(std::vector<bool> pattern) {
    std::vector<int> pattern_int(proba::NUM_BLOCKS, 0);
    for (int i = 0; i < proba::NUM_BLOCKS; i++)
        pattern_int[i] = (pattern[i] ? PF_FILL_L2 : 0);
    return pattern_int;
}

std::vector<int> rotate(const std::vector<int>& pattern, int offset) {
    size_t n = pattern.size();
    if (n == 0)
        return pattern;

    // Normalize offset into [0, n)
    int off = offset % static_cast<int>(n);
    if (off < 0)
        off += n;
    if (off == 0)
        return pattern;

    std::vector<int> result = pattern;
    std::rotate(result.begin(), result.end() - off, result.end());
    return result;
}

uint64_t random_gen() {
    return static_cast<uint64_t>(std::rand() % 100);
}

uint32_t count_bits_set(const std::vector<int> &pattern) {
    return std::count(pattern.begin(), pattern.end(), proba::PF_FILL_L2);
}

uint32_t count_bits_same(const std::vector<int> &pattern1, const std::vector<int> &pattern2) {
    assert(pattern1.size() == pattern2.size() && "Patterns must be the same length");

    uint32_t count = 0;
    for (size_t i = 0; i < pattern1.size(); ++i) {
        if (pattern1[i] == proba::PF_FILL_L2 && pattern2[i] == proba::PF_FILL_L2) {
            ++count;
        }
    }
    return count;
}


} // namespace proba

void CACHE::prefetcher_initialize() {
    std::cout << NAME << " Proba NEW NEW prefetcher" << std::endl;

    prefetchers = std::vector<proba::Proba>(NUM_CPUS, proba::Proba(proba::AGT_SIZE, proba::AGT_WAY, proba::PHT_SIZE, proba::PHT_WAY, proba::JT_SIZE, proba::PB_SIZE, proba::PB_WAY, proba::DEBUG, cpu));
}

uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint32_t metadata_in) {
    if (type != LOAD && type != PREFETCH)
        return metadata_in;

    uint64_t line_addr = (addr >> LOG2_BLOCK_SIZE); 
    uint64_t region_num = (addr >> LOG2_PAGE_SIZE);
    int offset = line_addr % proba::NUM_BLOCKS;

    prefetchers[cpu].set_warmup(warmup);

    uint64_t block_num = addr >> LOG2_BLOCK_SIZE;

    prefetchers[cpu].access(block_num, ip, this);
    prefetchers[cpu].prefetch(this, block_num);

    return metadata_in;
}

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    uint64_t evicted_block_num = evicted_addr >> LOG2_BLOCK_SIZE;

    prefetchers[cpu].eviction(evicted_block_num, this);

    return metadata_in;
}

void CACHE::prefetcher_cycle_operate() {}

void CACHE::prefetcher_final_stats() {
    prefetchers[cpu].log();
}