#include "proba_gaze.h"
#include "cache.h"

#include <assert.h>
#include <algorithm>
#include <array>

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

FilterTable::Entry FilterTable::insert(uint64_t region_num, uint64_t trigger_offset, uint64_t pc) {
    uint64_t key = build_key(region_num);
    auto old_entry = Super::insert(key, {trigger_offset, pc});
    Super::rp_insert(key);
    return old_entry;
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
    return key;
}

void FilterTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    // uint64_t key = custom_util::hash_index(entry.key, this->index_len);
    table.set_cell(row, 0, entry.key);
    table.set_cell(row, 1, entry.data.trigger_offset);
    table.set_cell(row, 2, entry.data.pc);
}

// ------------------------- AGT functions ------------------------- //
ActiveGenerationTable::ActiveGenerationTable(int size, int num_ways) :
    Super(size, num_ways) {}

ActiveGenerationTable::Entry* ActiveGenerationTable::set_pattern(uint64_t region_num, uint64_t offset) {
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

ActiveGenerationTable::Entry ActiveGenerationTable::insert(uint64_t region_num, uint64_t trigger_offset, uint64_t second_offset, uint64_t pc) {
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

ActiveGenerationTable::Entry* ActiveGenerationTable::erase(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    return Super::erase(key);
}

std::string ActiveGenerationTable::log() {
    std::vector<std::string> headers({"RegionNum", "Trigger", "Second", "PC", "Pattern", "Order"});
    return Super::log(headers);
}

void ActiveGenerationTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    // uint64_t key = custom_util::hash_index(entry.key, this->index_len);
    table.set_cell(row, 0, entry.key);
    table.set_cell(row, 1, entry.data.trigger_offset);
    table.set_cell(row, 2, entry.data.second_offset);
    table.set_cell(row, 3, entry.data.pc);
    table.set_cell(row, 4, custom_util::pattern_to_string(entry.data.pattern));
    table.set_cell(row, 5, custom_util::pattern_to_string(entry.data.order));
}

uint64_t ActiveGenerationTable::build_key(uint64_t region_num) {
    uint64_t key = region_num & ((1ULL << 37) - 1);
    return key;
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
    Entry* entry = Super::find(key);
    if (entry)
        Super::rp_promote(key);
    return entry;
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
    Entry* entry = Super::find(key);
    if (entry)
        Super::rp_promote(key);
    return entry;
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
PrefetchBuffer::PrefetchBuffer(int size, int pattern_len, int debug_level, int num_ways) :
    Super(size, num_ways), pattern_len(pattern_len) {
}

void PrefetchBuffer::insert(uint64_t region_num, std::vector<int> pattern) {
    uint64_t key = this->build_key(region_num);
    Entry* entry = Super::find(key);
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
                    if (ok) {
                        pf_issued += 1;
                        pattern[pf_offset] = 0;
                    }
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

ProbaGaze::ProbaGaze(int ft_size, int ft_ways, int agt_size, int agt_ways, int pht1_size, int pht1_ways, int pht2_size, int pht2_ways, int pb_size, int pb_ways, int jt_size, bool is_debug, int cpu) :
    ft(ft_size, ft_ways), agt(agt_size, agt_ways), pht1(pht1_size, pht1_ways), pht2(pht2_size, pht2_ways), pb(pb_size, NUM_BLOCKS, 0, pb_ways), jt(jt_size), is_debug(is_debug), cpu(cpu) {
}

void ProbaGaze::access(uint64_t block_num, uint64_t pc, CACHE* cache) {
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
        auto ft_entry = ft.find(region_num);
        if (!ft_entry) {
            if(!this->jt.in_jail(region_num)||!use_jail_table) {
                if (is_debug) {
                    std::cout << "Trigger access for PHT 1" <<std::endl;
                    std::cout << "pc: 0x" <<std::hex << pc << ", addr: 0x" << block_num << ", region: 0x" << region_num << ", offset: " << std::dec << region_offset << std::endl;
                }

                auto pht1_entry = pht1.find(pc);
                if(pht1_entry){
                    pb.insert(region_num, rotate(pht1_entry->data.pattern, region_offset));
                }
                
                int num_valid_entries = ft.get_num_valid_entries_per_set(region_num);
                
                bool sample = false;

                if(num_valid_entries<=(FT_WAY/2)){
                    if (is_debug) std::cout << "FT occupancy smaller than 50 percent, no sampling" <<std::endl;
                    sample=true;
                } else {
                    if (is_debug) std::cout << "FT occupancy greater than 50 percent, sampling" <<std::endl;
                    if(random_gen() < sample_rate){
                        sample=true;
                        if (is_debug) std::cout << "Region is sampled" <<std::endl;
                    } else {
                        if (is_debug) std::cout << "Region is not sampled" <<std::endl;
                    }
                }

                if(!use_sampling||sample){
                    auto ft_victim = ft.insert(region_num, region_offset, pc);
                    if (ft_victim.valid) {
                        jt.mark(ft_victim.key);
                    }
                } else {
                    jt.mark(region_num);
                    if (is_debug) std::cout << "Mark region 0x" << std::hex << region_num << std::dec << " in Jail Table" << std::endl;
                }
            }
        } else if (ft_entry->data.trigger_offset != region_offset) { // SECOND OFFSET
            if (is_debug) {
                std::cout << "Trigger access for PHT 2" <<std::endl;
                std::cout << "pc: 0x" <<std::hex << pc << ", addr: 0x" << block_num << ", region: 0x" << region_num << ", offset: " << std::dec << region_offset << std::endl;
            }
            // 1. find pht2 pattern
            auto pht2_entry = pht2.find(ft_entry->data.trigger_offset, region_offset);
            // pattern empty?
            bool pattern_empty = (!pht2_entry) || (2 == std::count_if(pht2_entry->data.pattern.begin(), pht2_entry->data.pattern.end(), [](auto& x) { return x != 0; }));

            if (!pattern_empty) {
                pb.insert(region_num, pht2_entry->data.pattern);
            }

            // 2. insert into at
            auto agt_victim = agt.insert(region_num, ft_entry->data.trigger_offset, region_offset, ft_entry->data.pc);
            ft.erase(region_num);
            if (agt_victim.valid) {
                jt.mark(agt_victim.key);
            //     update_in_pht1(agt_victim);
            //     update_in_pht2(agt_victim);
            }
        }
    }
}

void ProbaGaze::eviction(uint64_t block_num, CACHE* cache) {
    uint64_t region_num = block_num >> (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE);
    ft.erase(region_num);
    auto entry = agt.erase(region_num);
    if (entry) {
        update_in_pht1(*entry, cache);
        update_in_pht2(*entry, cache);
        if (is_debug) {
            std::cout << "In AGT, AGT erasing region: 0x" << std::hex << region_num << std::dec <<std::endl;
            std::cout << "PHT updating pc: 0x" << std::hex << entry->data.pc << std::dec << "\n" << pht1.log() << "\n" << pht2.log() <<std::endl;
        }
    } else {
        jt.unmark(region_num);
        if (is_debug) {
            std::cout << "Not in AGT, unmark region 0x" << std::hex << region_num << std::dec << " in Jail Table" << std::endl;
        }
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
    std::cout << this->agt.log();
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


void ProbaGaze::update_in_pht1(const ActiveGenerationTable::Entry& agt_entry, CACHE* cache) {
    auto pht1_entry = pht1.find(agt_entry.data.pc);
    if(pht1_entry){
        const std::vector<int> &observation = rotate(pattern_bool2int(agt_entry.data.pattern), -agt_entry.data.trigger_offset);
        std::vector<int> prediction = pht1_entry->data.pattern;
        custom_util::SaturatingCounter mode = pht1_entry->data.mode;

        assert(count_bits_same(prediction, observation) >= 1);

        auto safe_minus_one = [](uint32_t x) -> uint64_t {
            return (x > 0) ? static_cast<uint64_t>(x - 1) : 0ULL;
        };
        
        uint64_t pop_count_observation = safe_minus_one(count_bits_set(observation));
        uint64_t pop_count_prediction = safe_minus_one(count_bits_set(prediction));
        uint64_t same_count_observation_prediction = safe_minus_one(count_bits_same(prediction, observation));

        uint64_t local_accuracy = 0;
        {
            double tmp = 0.0;
            if (pop_count_prediction > 0) {
                tmp = (static_cast<double>(same_count_observation_prediction) /
                    static_cast<double>(pop_count_prediction)) * 100.0;
            }
            local_accuracy = static_cast<uint64_t>(tmp);
        }

        uint64_t local_acc_thr       = proba_acc_thr1;
        uint64_t corrected_accuracy  = local_accuracy;

        corrected_accuracy = std::clamp<uint64_t>(corrected_accuracy, 0, 100);
        local_acc_thr      = std::clamp<uint64_t>(local_acc_thr, 0, 100);

        if(pop_count_prediction > 0){
            if(corrected_accuracy > local_acc_thr) {
                mode.inc();
            } else {
                mode.dec();
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


void ProbaGaze::update_in_pht2(const ActiveGenerationTable::Entry& agt_entry, CACHE* cache) {
    auto pht2_entry = pht2.find(agt_entry.data.trigger_offset, agt_entry.data.second_offset);
    if(pht2_entry){
        const std::vector<int> &observation = pattern_bool2int(agt_entry.data.pattern);
        std::vector<int> prediction = pht2_entry->data.pattern;
        custom_util::SaturatingCounter mode = pht2_entry->data.mode;

        assert(count_bits_same(prediction, observation) >= 2);

        auto safe_minus_two = [](uint32_t x) -> uint64_t {
            return (x > 0) ? static_cast<uint64_t>(x - 2) : 0ULL;
        };
        
        uint64_t pop_count_observation = safe_minus_two(count_bits_set(observation));
        uint64_t pop_count_prediction = safe_minus_two(count_bits_set(prediction));
        uint64_t same_count_observation_prediction = safe_minus_two(count_bits_same(prediction, observation));

        uint64_t local_accuracy = 0;
        {
            double tmp = 0.0;
            if (pop_count_prediction > 0) {
                tmp = (static_cast<double>(same_count_observation_prediction) /
                    static_cast<double>(pop_count_prediction)) * 100.0;
            }
            local_accuracy = static_cast<uint64_t>(tmp);
        }

        uint64_t local_acc_thr       = proba_acc_thr2;
        uint64_t corrected_accuracy  = local_accuracy;

        corrected_accuracy = std::clamp<uint64_t>(corrected_accuracy, 0, 100);
        local_acc_thr      = std::clamp<uint64_t>(local_acc_thr, 0, 100);

        if(pop_count_prediction > 0){
            if(corrected_accuracy > local_acc_thr) {
                mode.inc();
            } else {
                mode.dec();
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


std::pair<uint64_t,uint64_t> ProbaGaze::get_probs(custom_util::SaturatingCounter mode) {
    assert(!(mode.get_cnt() < 0 || mode.get_cnt() > 7));

    static constexpr std::array<uint64_t,8> insert_probabilities = {
        1, 5, 10, 40, 100, 100, 100, 100
    };
    static constexpr std::array<uint64_t,8> delete_probabilities = {
        100, 100, 100, 100, 100, 60, 40, 20
    };
    return { insert_probabilities[mode.get_cnt()], delete_probabilities[mode.get_cnt()] };
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
    return std::count(pattern.begin(), pattern.end(), probagaze::PF_FILL_L2);
}

uint32_t count_bits_same(const std::vector<int> &pattern1, const std::vector<int> &pattern2) {
    assert(pattern1.size() == pattern2.size() && "Patterns must be the same length");

    uint32_t count = 0;
    for (size_t i = 0; i < pattern1.size(); ++i) {
        if (pattern1[i] == probagaze::PF_FILL_L2 && pattern2[i] == probagaze::PF_FILL_L2) {
            ++count;
        }
    }
    return count;
}


} // namespace probagaze

void CACHE::prefetcher_initialize() {
    std::cout << NAME << " Gaze NEW NEW prefetcher" << std::endl;

    prefetchers = std::vector<probagaze::ProbaGaze>(NUM_CPUS, probagaze::ProbaGaze(probagaze::FT_SIZE, probagaze::FT_WAY, probagaze::AGT_SIZE, probagaze::AGT_WAY, probagaze::PHT1_SIZE, probagaze::PHT1_WAY, probagaze::PHT2_SIZE, probagaze::PHT2_WAY, probagaze::PB_SIZE, probagaze::PB_WAY, probagaze::JT_SIZE, probagaze::IS_DEBUG, cpu));
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

    prefetchers[cpu].eviction(evicted_block_num, this);

    return metadata_in;
}

void CACHE::prefetcher_cycle_operate() {}

void CACHE::prefetcher_final_stats() {
    prefetchers[cpu].log();
}