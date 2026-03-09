#include "proba_gaze.h"
#include "cache.h"

#include <assert.h>
#include <algorithm>

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

static std::vector<probagaze::ProbaGaze> prefetchers;

namespace probagaze {

// ------------------------- FT functions ------------------------- //

FilterTable::FilterTable(int size, int num_ways) :
    Super(size, num_ways) {}

FilterTable::Entry* FilterTable::find(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    Entry* entry = Super::find(key);
    if (!entry) {
        return nullptr;
    } else {
        Super::rp_promote(key);
        return entry;
    }
}

void FilterTable::insert(uint64_t region_num, uint64_t trigger_offset, uint64_t pc) {
    uint64_t key = build_key(region_num);
    auto entry = Super::insert(key, {trigger_offset, pc});
    Super::rp_insert(key);
}

FilterTable::Entry* FilterTable::erase(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    return Super::erase(key);
}

std::string FilterTable::log() {
    std::vector<std::string> headers({"RegionNum", "Trigger", "PC"});
    return Super::log(headers);
}

uint64_t FilterTable::build_key(uint64_t region_num) {
    uint64_t key = region_num & ((1ULL << 37) - 1);
    return custom_util::hash_index(key, this->index_len);
}

void FilterTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    // uint64_t key = custom_util::hash_index(entry.key, this->index_len);
    table.set_cell(row, 0, entry.key);
    table.set_cell(row, 1, entry.data.trigger_offset);
    table.set_cell(row, 2, entry.data.pc);
}

// ------------------------- AT functions ------------------------- //
AccumulateTable::AccumulateTable(int size, int num_ways) :
    Super(size, num_ways) {}

AccumulateTable::Entry* AccumulateTable::set_pattern(uint64_t region_num, uint64_t offset) {
    uint64_t key = build_key(region_num);
    Entry* entry = Super::find(key);
    if (!entry)
        return nullptr;
    else {
        if (!entry->data.pattern[offset]) {
            entry->data.pattern[offset] = true;
        }
        Super::rp_promote(key);
        return entry;
    }
}

AccumulateTable::Entry AccumulateTable::insert(uint64_t region_num, uint64_t trigger_offset, uint64_t second_offset, uint64_t pc) {
    uint64_t key = build_key(region_num);
    std::vector<bool> pattern(NUM_BLOCKS, false);
    std::vector<int> order(NUM_BLOCKS, 0);
    pattern[trigger_offset] = pattern[second_offset] = true;
    order[trigger_offset] = 1;
    order[second_offset] = 2;
    Entry old_entry = Super::insert(key, {trigger_offset, second_offset, pc, pattern, order});
    Super::rp_insert(key);
    return old_entry;
}

AccumulateTable::Entry* AccumulateTable::erase(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    return Super::erase(key);
}

std::string AccumulateTable::log() {
    std::vector<std::string> headers({"RegionNum", "Trigger", "Second", "PC", "Pattern", "Order"});
    return Super::log(headers);
}

void AccumulateTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    // uint64_t key = custom_util::hash_index(entry.key, this->index_len);
    table.set_cell(row, 0, entry.key);
    table.set_cell(row, 1, entry.data.trigger_offset);
    table.set_cell(row, 2, entry.data.second_offset);
    table.set_cell(row, 3, entry.data.pc);
    table.set_cell(row, 4, custom_util::pattern_to_string(entry.data.pattern));
    table.set_cell(row, 5, custom_util::pattern_to_string(entry.data.order));
}

uint64_t AccumulateTable::build_key(uint64_t region_num) {
    uint64_t key = region_num & ((1ULL << 37) - 1);
    return custom_util::hash_index(key, this->index_len);
}

// ------------------------- PHT 1 functions ------------------------- //
PatternHistoryTable1::PatternHistoryTable1(int size, int num_ways) :
    Super(size, num_ways) {
    std::cout << "Pattern History Table 1 index_len: " << Super::index_len << std::endl;
}

void PatternHistoryTable1::insert(uint64_t pc, const std::vector<int> &pattern) {
    assert((int)pattern.size() == probagaze::NUM_BLOCKS);
    uint64_t key = build_key(pc);
    custom_util::SaturatingCounter mode(3,4);
    Super::insert(key, {pattern, mode});
    Super::rp_insert(key);  
}

void PatternHistoryTable1::update(uint64_t pc, const std::vector<int> &pattern, const custom_util::SaturatingCounter &mode) {
    assert((int)pattern.size() == probagaze::NUM_BLOCKS);
    uint64_t key = build_key(pc);
    Super::update(key, {pattern, mode});
    Super::rp_promote(key);  
}

PatternHistoryTable1::Entry* PatternHistoryTable1::find(uint64_t pc) {
    uint64_t key = build_key(pc);
    return Super::find(key);
}

std::string PatternHistoryTable1::log() {
    std::vector<std::string> headers({"Key", "Pattern", "Mode"});
    return Super::log(headers);
}

void PatternHistoryTable1::write_data(Entry& entry, custom_util::Table& table, int row) {
    table.set_cell(row, 0, entry.key);
    table.set_cell(row, 1, custom_util::pattern_to_string(entry.data.pattern));
    table.set_cell(row, 2, static_cast<int>(entry.data.mode.get_cnt()));
}

uint64_t PatternHistoryTable1::build_key(uint64_t pc) {
    return custom_util::hash_index(pc, this->index_len);
}

// ------------------------- PHT 2 functions ------------------------- //
PatternHistoryTable2::PatternHistoryTable2(int size, int num_ways) :
    Super(size, num_ways) {
    std::cout << "Pattern History Table 2 index_len: " << Super::index_len << std::endl;
}

void PatternHistoryTable2::insert(uint64_t trigger, uint64_t second, const std::vector<int> &pattern) {
    assert((int)pattern.size() == probagaze::NUM_BLOCKS);
    uint64_t key = build_key(trigger, second);
    custom_util::SaturatingCounter mode(3,4);
    Super::insert(key, {pattern, mode});
    Super::rp_insert(key);  
}

void PatternHistoryTable2::update(uint64_t trigger, uint64_t second, const std::vector<int> &pattern, const custom_util::SaturatingCounter &mode) {
    assert((int)pattern.size() == probagaze::NUM_BLOCKS);
    uint64_t key = build_key(trigger, second);
    Super::update(key, {pattern, mode});
    Super::rp_promote(key);  
}

PatternHistoryTable2::Entry* PatternHistoryTable2::find(uint64_t trigger, uint64_t second) {
    uint64_t key = build_key(trigger, second);
    return Super::find(key);
}

std::string PatternHistoryTable2::log() {
    std::vector<std::string> headers({"Trigger", "Second", "Pattern", "Mode"});
    return Super::log(headers);
}

void PatternHistoryTable2::write_data(Entry& entry, custom_util::Table& table, int row) {
    table.set_cell(row, 0, int(entry.key & uint64_t((1ULL << this->index_len) - 1)));
    table.set_cell(row, 1, int((entry.key >> this->index_len) & ((1ULL << this->index_len) - 1)));
    table.set_cell(row, 2, custom_util::pattern_to_string(entry.data.pattern));
    table.set_cell(row, 3, static_cast<int>(entry.data.mode.get_cnt()));
}

uint64_t PatternHistoryTable2::build_key(uint64_t trigger, uint64_t second) {
    assert(trigger >= 0 && trigger < NUM_BLOCKS && second >= 0 && second < NUM_BLOCKS);
    uint64_t key = (second << this->index_len) | trigger;
    return key;
}

// ------------------------- PB functions ------------------------- //
PrefetchBuffer::PrefetchBuffer(int size, int pattern_len, int debug_level = 0, int num_ways = 8) :
    Super(size, num_ways), pattern_len(pattern_len) {
}

void PrefetchBuffer::insert(uint64_t region_num, std::vector<int> pattern) {
    uint64_t key = this->build_key(region_num);
    auto entry = find(key);
    if (!entry) {
        Super::insert(key, {pattern});
        Super::rp_insert(key);
    } else { // hit in PHT1 then hit in PHT2
        for (int i = 0; i < NUM_BLOCKS; i++) {
            if (pattern[i] > 0) {
                entry->data.pattern[i] = PF_FILL_L2;
            }
        }
        Super::rp_promote(key);
    }
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

// ------------------------- ProbaGaze functions ------------------------- //

ProbaGaze::ProbaGaze(int ft_size, int ft_ways, int at_size, int at_ways, int pht1_size, int pht1_ways, int pht2_size, int pht2_ways, int pb_size, int pb_ways, int cpu = 0) :
    ft(ft_size, ft_ways), at(at_size, at_ways), pht1(pht1_size, pht1_ways), pht2(pht2_size, pht2_ways), pb(pb_size, NUM_BLOCKS, 0, pb_ways), cpu(cpu) {
}

void ProbaGaze::access(uint64_t block_num, uint64_t pc, CACHE* cache) {
    uint64_t region_num = block_num >> (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE);
    uint64_t region_offset = __region_offset(block_num);
    auto agt_entry = this->at.set_pattern(region_num, region_offset);
    if (agt_entry) {
        return;
    } else {
        auto ft_entry = ft.find(region_num);
        if (!ft_entry) {
            auto pht1_entry = pht1.find(pc);
            if(pht1_entry){
                pb.insert(region_num, rotate(pht1_entry->data.pattern, region_offset));
            }

            ft.insert(region_num, region_offset, pc);

            return;
        } else if (ft_entry->data.trigger_offset != region_offset) { // SECOND OFFSET
            // 1. find pht2 pattern
            auto pht2_entry = pht2.find(ft_entry->data.trigger_offset, region_offset);
            // pattern empty?
            bool pattern_empty = (!pht2_entry) || (2 == std::count_if(pht2_entry->data.pattern.begin(), pht2_entry->data.pattern.end(), [](auto& x) { return x != 0; }));

            if (!pattern_empty) {
                pb.insert(region_num, pht2_entry->data.pattern);
            }

            // 2. insert into at
            auto at_victim = at.insert(region_num, ft_entry->data.trigger_offset, region_offset, ft_entry->data.pc);
            ft.erase(region_num);
            if (at_victim.valid) {
                update_in_pht1(at_victim, region_num);
                update_in_pht2(at_victim, region_num);
            }
        }
    }
}

void ProbaGaze::eviction(uint64_t block_num) {
    uint64_t region_num = block_num >> (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE);
    ft.erase(region_num);
    auto entry = at.erase(region_num);
    if (entry) {
        update_in_pht1(*entry, region_num);
        update_in_pht2(*entry, region_num);
    }
}

void ProbaGaze::prefetch(CACHE* cache, uint64_t block_num) {
    pb.prefetch(cache, block_num);
}

void ProbaGaze::log() {
    std::cout << "Filter table begin" << std::dec << std::endl;
    std::cout << this->ft.log();
    std::cout << "Filter table end" << std::endl;

    std::cout << "Accumulation table begin" << std::dec << std::endl;
    std::cout << this->at.log();
    std::cout << "Accumulation table end" << std::endl;

    std::cout << "Pattern history table 1 begin" << std::dec << std::endl;
    std::cout << this->pht1.log();
    std::cout << "Pattern history table 1 end" << std::endl;

    std::cout << "Pattern history table 2 begin" << std::dec << std::endl;
    std::cout << this->pht2.log();
    std::cout << "Pattern history table 2 end" << std::endl;

    std::cout << "Prefetch buffer begin" << std::dec << std::endl;
    std::cout << this->pb.log();
    std::cout << "Prefetch buffer end" << std::endl;
}


void ProbaGaze::update_in_pht1(const AccumulateTable::Entry& agt_entry) {
    auto pht1_entry = pht1.find(agt_entry.data.pc);
    if(pht1_entry){
        const std::vector<int> &observation = rotate(pattern_bool2int(agt_entry.data.pattern), -agt_entry.data.trigger_offset);
        std::vector<int> prediction = pht1_entry->data.pattern;
        custom_util::SaturatingCounter mode = pht1_entry->data.mode;

        uint64_t pop_count_observation             = count_bits_set(observation) - 1;
        uint64_t pop_count_prediction              = count_bits_set(prediction) - 1;
        uint64_t same_count_observation_prediction = count_bits_same(prediction, observation) - 1;

        uint64_t local_accuracy = 0;
        {
            double tmp = 0.0;
            if (pop_count_prediction > 0) {
                tmp = (static_cast<double>(same_count_observation_prediction) /
                    static_cast<double>(pop_count_prediction)) * 100.0;
            }
            local_accuracy = static_cast<uint64_t>(tmp);
        }

        uint64_t local_acc_thr       = proba_acc_thr;
        uint64_t corrected_accuracy  = local_accuracy;

        corrected_accuracy = std::clamp<uint64_t>(corrected_accuracy, 0, 100);
        local_acc_thr      = std::clamp<uint64_t>(local_acc_thr, 0, 100);

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

        pht1.update(agt_entry.data.pc, prediction, mode);
    } else {
        if(count_bits_set(pattern_bool2int(agt_entry.data.pattern))>1){
            pht1.insert(agt_entry.data.pc, rotate(pattern_bool2int(agt_entry.data.pattern), -agt_entry.data.trigger_offset));
        }
    }
}


void ProbaGaze::update_in_pht2(const AccumulateTable::Entry& agt_entry) {
    auto pht2_entry = pht2.find(agt_entry.data.trigger_offset, agt_entry.data.second_offset);
    if(pht2_entry){
        const std::vector<int> &observation = pattern_bool2int(agt_entry.data.pattern);
        std::vector<int> prediction = pht2_entry->data.pattern;
        custom_util::SaturatingCounter mode = pht2_entry->data.mode;

        uint64_t pop_count_observation             = count_bits_set(observation) - 1;
        uint64_t pop_count_prediction              = count_bits_set(prediction) - 1;
        uint64_t same_count_observation_prediction = count_bits_same(prediction, observation) - 1;

        uint64_t local_accuracy = 0;
        {
            double tmp = 0.0;
            if (pop_count_prediction > 0) {
                tmp = (static_cast<double>(same_count_observation_prediction) /
                    static_cast<double>(pop_count_prediction)) * 100.0;
            }
            local_accuracy = static_cast<uint64_t>(tmp);
        }

        uint64_t local_acc_thr       = proba_acc_thr;
        uint64_t corrected_accuracy  = local_accuracy;

        corrected_accuracy = std::clamp<uint64_t>(corrected_accuracy, 0, 100);
        local_acc_thr      = std::clamp<uint64_t>(local_acc_thr, 0, 100);

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

        pht2.update(agt_entry.data.trigger_offset, agt_entry.data.second_offset, prediction, mode);
    } else {
        if(count_bits_set(pattern_bool2int(agt_entry.data.pattern))>2){
            pht2.insert(agt_entry.data.trigger_offset, agt_entry.data.second_offset, pattern_bool2int(agt_entry.data.pattern));
        }
    }
}

void ProbaGaze::set_warmup(bool warmup) {
    this->warmup = warmup;
    this->pb.warmup = warmup;
}

// ------------------------- util functions ------------------------- //
std::vector<int> pattern_bool2int(std::vector<bool> pattern) {
    std::vector<int> pattern_int(NUM_BLOCKS, 0);
    for (int i = 0; i < NUM_BLOCKS; i++)
        pattern_int[i] = (pattern[i] ? PF_FILL_L2 : 0);
    return pattern_int;
}

} // namespace probagaze

void CACHE::prefetcher_initialize() {
    std::cout << NAME << " Gaze NEW NEW prefetcher" << std::endl;

    prefetchers = std::vector<probagaze::ProbaGaze>(NUM_CPUS, probagaze::ProbaGaze(probagaze::FT_SIZE, probagaze::FT_WAY, probagaze::AT_SIZE, probagaze::AT_WAY, probagaze::PHT1_SIZE, probagaze::PHT1_WAY, probagaze::PHT2_SIZE, probagaze::PHT2_WAY, probagaze::PB_SIZE, probagaze::PB_WAY, cpu));
}

uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint32_t metadata_in) {
    uint64_t line_addr = (addr >> LOG2_BLOCK_SIZE); 
    uint64_t region_num = (addr >> LOG2_PAGE_SIZE);
    int offset = line_addr % probagaze::NUM_BLOCKS;

    prefetchers[cpu].set_warmup(warmup);

    if (type != LOAD && type != PREFETCH)
        return metadata_in;
    uint64_t block_num = addr >> LOG2_BLOCK_SIZE;

    prefetchers[cpu].access(block_num, ip, this);
    prefetchers[cpu].prefetch(this, block_num);

    return metadata_in;
}

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    uint64_t evicted_block_num = evicted_addr >> LOG2_BLOCK_SIZE;

    for (int i = 0; i < NUM_CPUS; i += 1) {
        prefetchers[i].eviction(evicted_block_num);
    }

    return metadata_in;
}

void CACHE::prefetcher_cycle_operate() {}

void CACHE::prefetcher_final_stats() {
    prefetchers[cpu].log();
}