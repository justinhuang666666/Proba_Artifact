#include "proba.h"
#include "cache.h"

#include <assert.h>
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

static std::vector<proba::Proba> prefetchers;

namespace proba {



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

void FilterTable::insert(uint64_t region_num, uint64_t trigger_offset) {
    uint64_t key = build_key(region_num);
    auto entry = Super::insert(key, {trigger_offset});
    Super::rp_insert(key);
}

FilterTable::Entry* FilterTable::erase(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    return Super::erase(key);
}

std::string FilterTable::log() {
    std::vector<std::string> headers({"RegionNum", "Trigger"});
    return Super::log(headers);
}

uint64_t FilterTable::build_key(uint64_t region_num) {
    uint64_t key = region_num & ((1ULL << 37) - 1);
    return custom_util::hash_index(key, this->index_len);
}

void FilterTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    table.set_cell(row, 0, entry.key);
    table.set_cell(row, 1, entry.data.trigger_offset);
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
        entry->data.pattern[offset] = true;
        if(entry->data.second_offset == proba::NUM_BLOCKS && offset != entry->data.trigger_offset) entry->data.second_offset=offset;
        Super::rp_promote(key);
        return entry;
    }
}

ActiveGenerationTable::Entry ActiveGenerationTable::insert(uint64_t region_num, uint64_t trigger_offset, uint64_t pc, uint64_t addr) {
    uint64_t key = build_key(region_num);
    std::vector<bool> pattern(NUM_BLOCKS, false);
    pattern[trigger_offset] = true;
    Entry old_entry = Super::insert(key, {trigger_offset, proba::NUM_BLOCKS, pc, addr, pattern});
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
    std::vector<std::string> headers({"RegionNum", "Trigger Offset", "Second Offset", "PC", "Addr", "Pattern"});
    return Super::log(headers);
}

void ActiveGenerationTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    table.set_cell(row, 0, entry.key);
    table.set_cell(row, 1, entry.data.trigger_offset);
    table.set_cell(row, 2, entry.data.second_offset);
    table.set_cell(row, 3, entry.data.pc);
    table.set_cell(row, 4, entry.data.addr);
    table.set_cell(row, 5, custom_util::pattern_to_string(entry.data.pattern));
}

uint64_t ActiveGenerationTable::build_key(uint64_t region_num) {
    uint64_t key = region_num & ((1ULL << 37) - 1);
    return key;
}


// ------------------------- PHT functions ------------------------- //
PatternHistoryTable::PatternHistoryTable(int size, int num_ways, int width, Behavior behavior) :
    Super(size, num_ways), width(width), behavior(behavior) {
    std::cout << "Pattern Table index_len: " << Super::index_len << std::endl;
}

void PatternHistoryTable::insert(uint64_t pc, uint64_t offset1, uint64_t offset2, uint64_t addr, const std::vector<int> &pattern) {
    assert((int)pattern.size() == proba::NUM_BLOCKS);
    uint64_t key = build_key(pc, offset1, offset2, addr);
    // std::cout<<"pc key: "<<std::hex<<key<<std::dec<<std::endl;
    custom_util::SaturatingCounter mode(3,4);
    Super::insert(key, {pattern, mode});
    Super::rp_insert(key);
}

void PatternHistoryTable::update(uint64_t pc, uint64_t offset1, uint64_t offset2, uint64_t addr, const std::vector<int> &pattern, const custom_util::SaturatingCounter &mode) {
    assert((int)pattern.size() == proba::NUM_BLOCKS);
    uint64_t key = build_key(pc, offset1, offset2, addr);
    // std::cout<<"pc key: "<<std::hex<<key<<std::dec<<std::endl;
    Super::update(key, {pattern, mode});
    Super::rp_promote(key);
}

void PatternHistoryTable::update_no_touch(uint64_t pc, uint64_t offset1, uint64_t offset2, uint64_t addr, const std::vector<int> &pattern, const custom_util::SaturatingCounter &mode) {
    assert((int)pattern.size() == proba::NUM_BLOCKS);
    uint64_t key = build_key(pc, offset1, offset2, addr);
    // std::cout<<"pc key: "<<std::hex<<key<<std::dec<<std::endl;
    Super::update(key, {pattern, mode});
}

PatternHistoryTable::Entry* PatternHistoryTable::find(uint64_t pc, uint64_t offset1, uint64_t offset2, uint64_t addr) {
    if(offset2 == proba::NUM_BLOCKS && behavior == PatternHistoryTable::Behavior::OffsetOffset) return nullptr;
    uint64_t key = build_key(pc, offset1, offset2, addr);
    Entry* entry = Super::find(key);
    if (entry)
        Super::rp_promote(key);
    return entry;
}

PatternHistoryTable::Entry* PatternHistoryTable::find_no_touch(uint64_t pc, uint64_t offset1, uint64_t offset2, uint64_t addr) {
    if(offset2 == proba::NUM_BLOCKS && behavior == PatternHistoryTable::Behavior::OffsetOffset) return nullptr;
    uint64_t key = build_key(pc, offset1, offset2, addr);
    Entry* entry = Super::find(key);
    return entry;
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

// uint64_t PatternHistoryTable::build_key(uint64_t pc) {
//     return custom_util::hash_index(pc, this->index_len);
// }
uint64_t PatternHistoryTable::build_key(uint64_t pc, uint64_t offset1, uint64_t offset2, uint64_t addr) {
    uint64_t base_key = 0;

    switch (behavior)
    {
    case PatternHistoryTable::Behavior::PC:

        // Use PC only
        base_key = custom_util::folded_xor(pc, 4);
        break;

    case PatternHistoryTable::Behavior::PCOffset:
        base_key = custom_util::folded_xor(pc, 4);
        base_key = (base_key << proba::OFFSET_WIDTH) | offset1;
        // Use PC + offset
        break;

    case PatternHistoryTable::Behavior::PCAddr:
        base_key = get_hash(custom_util::folded_xor(pc, 4)) ^ get_hash(addr);
        break;

    case PatternHistoryTable::Behavior::Offset:
        // Use offset only
        base_key=offset1;
        break;

    case PatternHistoryTable::Behavior::OffsetOffset:
        base_key = (offset2 << proba::OFFSET_WIDTH) | offset1;
        // Use offset + offset (two-level offset scheme)
        break;

    default:
        // Should never happen
        break;
    }
    uint32_t hashed_key = get_hash(base_key); //truncation alert...
    uint64_t mask = (this->width >= 32) ? 0xFFFFFFFFULL : ((1ULL << this->width) - 1ULL);

    return hashed_key & mask;
}

uint32_t PatternHistoryTable::get_hash(uint32_t key) {
    switch (proba::PROBA_HASH_TYPE) {
    case 1:
        return key;
    case 2:
        return custom_util::HashZoo::jenkins(key);
    case 3:
        return custom_util::HashZoo::knuth(key);
    case 4:
        return custom_util::HashZoo::murmur3(key);
    case 5:
        return custom_util::HashZoo::jenkins32(key);
    case 6:
        return custom_util::HashZoo::hash32shift(key);
    case 7:
        return custom_util::HashZoo::hash32shiftmult(key);
    case 8:
        return custom_util::HashZoo::hash64shift(key);
    case 9:
        return custom_util::HashZoo::hash5shift(key);
    case 10:
        return custom_util::HashZoo::hash7shift(key);
    case 11:
        return custom_util::HashZoo::Wang6shift(key);
    case 12:
        return custom_util::HashZoo::Wang5shift(key);
    case 13:
        return custom_util::HashZoo::Wang4shift(key);
    case 14:
        return custom_util::HashZoo::Wang3shift(key);
    default:
        assert(false);
    }
}

// ------------------------- PB functions ------------------------- //
PrefetchBuffer::PrefetchBuffer(int size, int pattern_len, int debug_level, int num_ways) :
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
    auto entry = find(key);
    if (!entry) {
        Super::insert(key, {pattern});
        Super::rp_insert(key);
    } else {
        for (int i = 0; i < NUM_BLOCKS; i++) {
            if (pattern[i] == PF_FILL_L2) {
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

// ------------------------- Proba functions ------------------------- //

Proba::Proba(int agt_size, int agt_ways, int ft_size, int ft_ways, int pht_size, int pht_ways, int width, int jt_size, int pb_size, int pb_ways, int accuracy_threshold, int marginal_accuracy_threshold, bool is_debug, int cpu) :
    agt(agt_size, agt_ways),
    phts(std::vector<PatternHistoryTable>{
    //   PatternHistoryTable(pht_size*pht_size, pht_ways, width, PatternHistoryTable::Behavior::PCAddr),
        PatternHistoryTable(pht_size, pht_ways, width, PatternHistoryTable::Behavior::OffsetOffset),
        PatternHistoryTable(pht_size, pht_ways, width, PatternHistoryTable::Behavior::PCOffset),
        PatternHistoryTable(pht_size, pht_ways, width, PatternHistoryTable::Behavior::PC),
        PatternHistoryTable(NUM_BLOCKS, 1, width, PatternHistoryTable::Behavior::Offset)
    }),
    jt(jt_size),
    ft(ft_size, ft_ways), 
    pb(pb_size, NUM_BLOCKS, 0, pb_ways), 
    proba_acc_thr1(accuracy_threshold), proba_acc_thr2(marginal_accuracy_threshold),
    is_debug(is_debug), cpu(cpu) {
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
        100, 100, 100, 100, 100, 40, 20, 10
    };
    return { insert_probabilities[mode.get_cnt()], delete_probabilities[mode.get_cnt()] };
}

void Proba::access(uint64_t block_num, uint64_t pc, CACHE* cache) {
    uint64_t region_num = block_num >> (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE);
    uint64_t region_offset = __region_offset(block_num);
    auto agt_entry = this->agt.set_pattern(region_num, region_offset);

    //TODO: insert check for filter table as well for Gaze.
    int offset2=proba::NUM_BLOCKS;
    auto ft_entry = ft.find(region_num);
    if (!ft_entry && !agt_entry && (!this->jt.in_jail(region_num)||!use_jail_table)) {
        ft.insert(region_num, region_offset);
        if (is_debug) {
            std::cout << "Access: FT detects first offset for region: 0x" << std::hex << region_num  << ", offset: " << std::dec << region_offset << std::endl;
        }
    } else if (ft_entry && ft_entry->data.trigger_offset != region_offset) { // SECOND OFFSET
        offset2 = region_offset;
        region_offset = ft_entry->data.trigger_offset;
        ft.erase(region_num);
        if (is_debug) {
            std::cout << "Access: FT detects second offset for region: 0x" << std::hex << region_num  << ", offset: " << std::dec << region_offset << std::endl;
        }
    }

    if (agt_entry) {
        if (is_debug) {
            std::cout << "Access: Matching AGT entry, appending offset" <<std::endl;
            std::cout << "pc: 0x" <<std::hex << pc << ", addr: 0x" << block_num << ", region: 0x" << region_num << ", offset: " << std::dec << region_offset << std::endl;
        }
    }

    if(!agt_entry || offset2 != proba::NUM_BLOCKS) {
        if(offset2 != proba::NUM_BLOCKS || (!this->jt.in_jail(region_num)||!use_jail_table)) {
            if (is_debug) {
                std::cout << "Access: Trigger access" <<std::endl;
                std::cout << "pc: 0x" <<std::hex << pc << ", addr: 0x" << block_num << ", region: 0x" << region_num << ", offset: " << std::dec << region_offset << std::endl;
            }

            std::vector<int> accumulated_pattern;

            // Loop over all PHTs
            for (auto& table : phts) {
                if(offset2 !=proba::NUM_BLOCKS && table.behavior != PatternHistoryTable::Behavior::OffsetOffset) continue;
                if(offset2 ==proba::NUM_BLOCKS && table.behavior == PatternHistoryTable::Behavior::OffsetOffset) continue;
                auto entry = table.find(pc, region_offset, offset2, block_num);
                if (!entry) continue;

                auto aligned_pattern = (table.behavior == PatternHistoryTable::Behavior::PC) ? rotate(entry->data.pattern, region_offset) : entry->data.pattern;

                auto behavior_to_string = [](PatternHistoryTable::Behavior behavior) -> const char* {
                    switch (behavior) {
                        case PatternHistoryTable::Behavior::PC: return "PC";
                        case PatternHistoryTable::Behavior::PCOffset: return "PCOffset";
                        case PatternHistoryTable::Behavior::PCAddr: return "PCAddr";
                        case PatternHistoryTable::Behavior::Offset: return "Offset";
                        case PatternHistoryTable::Behavior::OffsetOffset: return "OffsetOffset";
                        default: return "Unknown";
                    }
                };

                if (is_debug) {
                    std::cout << "Table behavior:      " << behavior_to_string(table.behavior) << std::endl;
                    std::cout << "Pattern:             " << custom_util::pattern_to_string(aligned_pattern) <<std::endl;
                }
                
                if (accumulated_pattern.empty()) {
                    accumulated_pattern = aligned_pattern;
                } else {
                    accumulated_pattern = union_patterns(accumulated_pattern, aligned_pattern);
                }
            }

            // After unioning all patterns, insert
            if (!accumulated_pattern.empty()) {

                pb.insert(region_num, accumulated_pattern); 

                if (is_debug) {
                    std::cout << "Accumulated pattern: " << custom_util::pattern_to_string(accumulated_pattern) << std::endl;
                }
            }

            if(offset2 ==proba::NUM_BLOCKS) {
                int num_valid_entries = agt.get_num_valid_entries_per_set(region_num);

                bool sample = false;

                if(num_valid_entries<=(AGT_WAY/2)) {
                    if (is_debug) std::cout << "Access: AGT occupancy smaller than 50 percent, no sampling" <<std::endl;
                    sample=true;
                } else {
                    if (is_debug) std::cout << "Access: AGT occupancy greater than 50 percent, sampling" <<std::endl;
                    if(random_gen() < sample_rate) {
                        sample=true;
                        if (is_debug) std::cout << "Region is sampled" <<std::endl;
                    } else {
                        if (is_debug) std::cout << "Region is not sampled" <<std::endl;
                    }
                }

                if(!use_sampling||sample) {
                    auto agt_victim = agt.insert(region_num, region_offset, pc,block_num);

                    if (is_debug) {
                        std::cout << "Access: AGT inserting region 0x" << std::hex << region_num << "pc: 0x" << pc << std::dec << ", offset: " << region_offset << std::endl;
                        std::cout << agt.log() << std::endl;
                    }

                    if (agt_victim.valid) {
                        update_in_pht(agt_victim, false, cache);
                    }
                } else {
                    jt.mark(region_num);
                    if (is_debug) std::cout << "Access: Mark region 0x" << std::hex << region_num << std::dec << " in Jail Table" << std::endl;
                }
            }
        }
    }
    return;
}

void Proba::eviction(uint64_t block_num, CACHE* cache) {
    uint64_t region_num = block_num >> (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE);
    uint64_t region_offset = __region_offset(block_num);
    ft.erase(region_num);
    auto entry = agt.erase(region_num);

    if (entry) {
        if (is_debug) {
            std::cout << "Eviction: in AGT, AGT erasing region: 0x" << std::hex << region_num << ", offset: "<< std::dec << region_offset << std::endl;
        }
        update_in_pht(*entry, true, cache);
    } else {
        if (is_debug) {
            std::cout << "Eviction: not in AGT, unmark region 0x" << std::hex << region_num << std::dec << " in Jail Table" << std::endl;
        }
        jt.unmark(region_num);
    }
}

int Proba::prefetch(CACHE* cache, uint64_t block_num) {
    return pb.prefetch(cache, block_num);
}

void Proba::log() {
    // std::cout << "Accumulation table begin" << std::dec << std::endl;
    // std::cout << this->agt.log();
    // std::cout << "Accumulation table end" << std::endl;

    //std::cout << "Pattern table begin" << std::dec << std::endl;
    //std::cout << this->pht.log();
    //std::cout << "Pattern table end" << std::endl;

    // std::cout << "Prefetch buffer begin" << std::dec << std::endl;
    // std::cout << this->pb.log();
    // std::cout << "Prefetch buffer end" << std::endl;
}

void Proba::update_in_pht(const ActiveGenerationTable::Entry& agt_entry, bool is_end_of_generation, CACHE* cache) {
    if (is_end_of_generation) {
        if (is_debug) std::cout << "Update: AGT end-of-generation eviction" << std::endl;
    } else {
        jt.mark(agt_entry.key);
        if (is_debug) std::cout << "Update: AGT capacity eviction, mark region 0x" << std::hex << agt_entry.key << std::dec << std::endl;
    }

    if (use_only_training_on_eog && !is_end_of_generation)
        return;

    const bool has_second = (agt_entry.data.second_offset != proba::NUM_BLOCKS);

    auto behavior_to_string = [](PatternHistoryTable::Behavior behavior) -> const char* {
        switch (behavior) {
            case PatternHistoryTable::Behavior::PC: return "PC";
            case PatternHistoryTable::Behavior::PCOffset: return "PCOffset";
            case PatternHistoryTable::Behavior::PCAddr: return "PCAddr";
            case PatternHistoryTable::Behavior::Offset: return "Offset";
            case PatternHistoryTable::Behavior::OffsetOffset: return "OffsetOffset";
            default: return "Unknown";
        }
    };

    auto get_observation_for_table =
        [&](const PatternHistoryTable& table) -> std::vector<int> {
            std::vector<int> obs = pattern_bool2int(agt_entry.data.pattern);
            obs[agt_entry.data.trigger_offset] = 0;
            if (table.behavior == PatternHistoryTable::Behavior::OffsetOffset) {
                obs[agt_entry.data.second_offset] = 0;
            }
            if (table.behavior == PatternHistoryTable::Behavior::PC) {
                obs = rotate(obs, -static_cast<int>(agt_entry.data.trigger_offset));
            }
            return obs;
        };

    auto get_prediction_for_table =
        [&](const PatternHistoryTable& table,
            const std::vector<int>& stored_pattern) -> std::vector<int> {
            std::vector<int> pred = stored_pattern;
            if (table.behavior == PatternHistoryTable::Behavior::PC) {
                pred[0] = 0;
            } else {
                pred[agt_entry.data.trigger_offset] = 0;
            }
            if (table.behavior == PatternHistoryTable::Behavior::OffsetOffset) {
                pred[agt_entry.data.second_offset] = 0;
            }
            return pred;
        };

    auto get_stored_pattern_for_table =
        [&](const PatternHistoryTable& table) -> std::vector<int> {
            std::vector<int> pat = pattern_bool2int(agt_entry.data.pattern);
            if (table.behavior == PatternHistoryTable::Behavior::PC) {
                pat[agt_entry.data.trigger_offset] = 0;
                pat = rotate(pat, -static_cast<int>(agt_entry.data.trigger_offset));
            } else {
                pat[agt_entry.data.trigger_offset] = 0;
            }
            if (table.behavior == PatternHistoryTable::Behavior::OffsetOffset) {
                pat[agt_entry.data.second_offset] = 0;
            }
            return pat;
        };

    std::vector<int> accuracy(phts.size(), 0);
    std::vector<int> accumulated_prediction;
    std::vector<size_t> active_indices;
    std::vector<bool> touches(pht.size(),false);

    if(is_debug) std::cout << "Observation:        " << custom_util::pattern_to_string(agt_entry.data.pattern) << std::endl;

    for (size_t tidx = 0; tidx < phts.size(); ++tidx) {
        auto& table = phts[tidx];

        // if (has_second && table.behavior != PatternHistoryTable::Behavior::OffsetOffset) continue;
        if (!has_second && table.behavior == PatternHistoryTable::Behavior::OffsetOffset) continue;

        active_indices.push_back(tidx);

        std::vector<int> observation = get_observation_for_table(table);

        touches[tidx] = (count_bits_set(observation) > 0);

        uint64_t local_accuracy = 0;
        auto pht_entry = table.find_no_touch(agt_entry.data.pc, agt_entry.data.trigger_offset, agt_entry.data.second_offset, agt_entry.data.addr);

        if (pht_entry) {
            if (is_debug) std::cout << "Update: PHT entry found" << std::endl;

            std::vector<int> prediction = get_prediction_for_table(table, pht_entry->data.pattern);

            if (accumulated_prediction.empty()) {
                accumulated_prediction = (table.behavior == PatternHistoryTable::Behavior::PC) ? rotate(prediction, agt_entry.data.trigger_offset) : prediction;
            } else {
                accumulated_prediction = union_patterns(accumulated_prediction, (table.behavior == PatternHistoryTable::Behavior::PC) ? rotate(prediction, agt_entry.data.trigger_offset) : prediction);
            }

            if (is_debug) {
                std::cout << "Table behavior:     " << behavior_to_string(table.behavior) << std::endl;
                std::cout << "Observation:        " << custom_util::pattern_to_string(observation) << std::endl;
                std::cout << "Prediction:         " << custom_util::pattern_to_string(prediction) << std::endl;
            }

            uint64_t pop_count_prediction = count_bits_set(prediction);
            uint64_t same_count_observation_prediction = count_bits_same(prediction, observation);

            if (pop_count_prediction > 0) {
                local_accuracy =
                    (100ULL * same_count_observation_prediction) / pop_count_prediction;
            }

            if (is_debug) {
                std::cout << "same_count_observation_prediction: " << same_count_observation_prediction << std::endl;
                std::cout << "pop_count_prediction:              " << pop_count_prediction << std::endl;
                std::cout << "Local Accuracy:                    " << local_accuracy << std::endl;
            }
        }

        accuracy[tidx] = local_accuracy;
    }

    // calibration
    std::vector<int> accumulated_observation = pattern_bool2int(agt_entry.data.pattern);
    accumulated_observation[agt_entry.data.trigger_offset] = 0;

    uint64_t pop_count_accumulated_prediction = count_bits_set(accumulated_prediction);
    uint64_t same_count_accumulated_observation_accumulated_prediction = count_bits_same(accumulated_prediction, accumulated_observation);
    global_accurate_pf_sum += same_count_accumulated_observation_accumulated_prediction;
    global_pf_sum += pop_count_accumulated_prediction;
    num_valid_update++;
    total_num_valid_update++;
    
    if (num_valid_update >= ewma_window_size) {
        uint64_t window_accuracy_estimate = 0;
    
        if (global_pf_sum > 0) {
            window_accuracy_estimate =
                (100ULL * global_accurate_pf_sum) / global_pf_sum;
        }
    
        uint64_t cur_pf_useful = static_cast<uint64_t>(cache->sim_stats.pf_useful);
        uint64_t cur_pf_unused = static_cast<uint64_t>(cache->sim_stats.pf_useless);
    
        uint64_t window_pf_useful = 0;
        uint64_t window_pf_unused = 0;
    
        if (cur_pf_useful >= prev_pf_useful && cur_pf_unused >= prev_pf_unused) {
            window_pf_useful = cur_pf_useful - prev_pf_useful;
            window_pf_unused = cur_pf_unused - prev_pf_unused;
        }
    
        uint64_t window_global_accuracy = 0;
        if (window_pf_useful + window_pf_unused > 0) {
            window_global_accuracy =
                (100ULL * window_pf_useful) / (window_pf_useful + window_pf_unused);
        }
    
        bool first_window = (total_num_valid_update == num_valid_update);
    
        if (first_window) {
            ewma_accuracy_estimate = window_accuracy_estimate;
            ewma_global_accuracy = window_global_accuracy;
        } else if (cur_pf_useful >= prev_pf_useful && cur_pf_unused >= prev_pf_unused) {
            ewma_update(ewma_accuracy_estimate, window_accuracy_estimate,
                        ewma_alpha_num, ewma_alpha_den);
            ewma_update(ewma_global_accuracy, window_global_accuracy,
                        ewma_alpha_num, ewma_alpha_den);
        }
    
        global_accurate_pf_sum = 0;
        global_pf_sum = 0;
        prev_pf_useful = cur_pf_useful;
        prev_pf_unused = cur_pf_unused;
        num_valid_update = 0;
    }

    std::sort(active_indices.begin(), active_indices.end(),[&](size_t a, size_t b) { return accuracy[a] > accuracy[b];});

    bool first_iteration = true;

    std::vector<int> accumulated_marginal_prediction;

    for (size_t idx : active_indices) {
        auto& table = phts[idx];
        auto pht_entry = table.find_no_touch(agt_entry.data.pc, agt_entry.data.trigger_offset, agt_entry.data.second_offset, agt_entry.data.addr);
        
        if (!pht_entry) continue;

        std::vector<int> observation = get_observation_for_table(table);
        std::vector<int> prediction = get_prediction_for_table(table, pht_entry->data.pattern);

        if (first_iteration) {
            if (is_debug) std::cout << "Marginal accuracy first iteration"<< std::endl;
            first_iteration = false;

            uint64_t local_accuracy = accuracy[idx];
            uint64_t estimated_global_accuracy = ewma_accuracy_estimate;

            int64_t local_acc_thr = proba_acc_thr1;
            int64_t corrected_accuracy = static_cast<int64_t>(local_accuracy);

            if (is_accuracy_targeter && ewma_global_accuracy != 0) {
                int64_t act = static_cast<int64_t>(ewma_global_accuracy);
                int64_t thr = static_cast<int64_t>(proba_acc_thr1);
                local_acc_thr = 2 * thr - act;
            }

            if (is_accuracy_correction && estimated_global_accuracy != 0) {
                int64_t loc = static_cast<int64_t>(local_accuracy);
                int64_t act = static_cast<int64_t>(ewma_global_accuracy);
                int64_t est = static_cast<int64_t>(estimated_global_accuracy);
                corrected_accuracy = (loc * act) / est;
            }

            local_acc_thr = std::clamp<int64_t>(local_acc_thr, 0, 100);
            corrected_accuracy = std::clamp<int64_t>(corrected_accuracy, 0, 100);

            if (is_debug) {
                std::cout << "Table behavior:            " << behavior_to_string(table.behavior) << std::endl;
                std::cout << "Local Accuracy:            " << local_accuracy << std::endl;
            }

            uint64_t pop_count_prediction = count_bits_set(prediction);

            if (pop_count_prediction > 0) {
                if (corrected_accuracy > local_acc_thr) {
                    pht_entry->data.mode.inc();
                    if (is_debug) {
                        std::cout << "Accuracy greater than threshold, increment mode: " << pht_entry->data.mode.get_cnt() << std::endl;
                    }
                } else {
                    pht_entry->data.mode.dec();
                    if (is_debug) {
                        std::cout << "Accuracy less than threshold, decrement mode: " << pht_entry->data.mode.get_cnt() << std::endl;
                    }
                }
            }

            accumulated_marginal_prediction = (table.behavior == PatternHistoryTable::Behavior::PC) ? rotate(prediction, agt_entry.data.trigger_offset) : prediction;
            if (is_debug) std::cout << "accumulated_marginal_prediction: " << custom_util::pattern_to_string(accumulated_marginal_prediction) << std::endl;
        } else {
            if (is_debug) {
                std::cout << "Marginal accuracy iteration"<< std::endl;
                std::cout << "Table behavior:            " << behavior_to_string(table.behavior) << std::endl;
            }

            std::vector<int> marginal_prediction = prediction;
            std::vector<int> marginal_obs = observation;

            if (is_debug) {
                std::cout << "prediction:                      " << custom_util::pattern_to_string(marginal_prediction) << std::endl;
                std::cout << "obs:                             " << custom_util::pattern_to_string(marginal_obs) << std::endl;
            }
            auto aligned_accumulated_marginal_prediction = (table.behavior == PatternHistoryTable::Behavior::PC) ? rotate(accumulated_marginal_prediction, -agt_entry.data.trigger_offset) : accumulated_marginal_prediction;
            for (size_t i = 0; i < aligned_accumulated_marginal_prediction.size(); ++i) {
                if (aligned_accumulated_marginal_prediction[i] != 0) {
                    marginal_prediction[i] = 0;
                    marginal_obs[i] = 0;
                }
            }

            if (is_debug) {
                std::cout << "marginal_prediction:             " << custom_util::pattern_to_string(marginal_prediction) << std::endl;
                std::cout << "marginal_obs:                    " << custom_util::pattern_to_string(marginal_obs) << std::endl;
            }

            uint64_t pop_count_prediction = count_bits_set(marginal_prediction);
            uint64_t same_count_observation_prediction = count_bits_same(marginal_prediction, marginal_obs);

            uint64_t local_maccuracy = 0;
            if (pop_count_prediction > 0) {
                local_maccuracy =
                    (100ULL * same_count_observation_prediction) / pop_count_prediction;
            }

            if (is_debug) {
                std::cout << "Local Marginal Accuracy:            " << local_maccuracy << std::endl;
            }

            int64_t local_acc_thr = proba_acc_thr2;
            int64_t corrected_accuracy = static_cast<int64_t>(local_maccuracy);

            if (is_accuracy_targeter && ewma_global_accuracy != 0) {
                int64_t act = static_cast<int64_t>(ewma_global_accuracy);
                int64_t thr = static_cast<int64_t>(proba_acc_thr2);
                local_acc_thr = 2 * thr - act;
            }

            if (is_accuracy_correction && ewma_accuracy_estimate != 0) {
                int64_t loc = static_cast<int64_t>(local_maccuracy);
                int64_t act = static_cast<int64_t>(ewma_global_accuracy);
                int64_t est = static_cast<int64_t>(ewma_accuracy_estimate);
                corrected_accuracy = (loc * act) / est;
            }

            local_acc_thr = std::clamp<int64_t>(local_acc_thr, 0, 100);
            corrected_accuracy = std::clamp<int64_t>(corrected_accuracy, 0, 100);

            if (pop_count_prediction > 0) {
                if (corrected_accuracy > local_acc_thr) {
                    pht_entry->data.mode.inc();
                    if (is_debug) {
                        std::cout << "Accuracy greater than threshold, increment mode: " << pht_entry->data.mode.get_cnt() << std::endl;
                    }
                } else {
                    pht_entry->data.mode.dec();
                    if (is_debug) {
                        std::cout << "Accuracy less than threshold, decrement mode: " << pht_entry->data.mode.get_cnt() << std::endl;
                    }
                }
            }
            accumulated_marginal_prediction = union_patterns(accumulated_marginal_prediction,(table.behavior == PatternHistoryTable::Behavior::PC) ? rotate(prediction, agt_entry.data.trigger_offset) : prediction);
            if (is_debug) std::cout << "accumulated_marginal_prediction: " << custom_util::pattern_to_string(accumulated_marginal_prediction) << std::endl;
        }
    }

    if (is_debug) std::cout << "Update PHT using marginal accuracy"<< std::endl;

    for (size_t idx : active_indices) {
        auto& table = phts[idx];

        std::vector<int> observation = get_observation_for_table(table);

        auto pht_entry = table.find_no_touch(agt_entry.data.pc, agt_entry.data.trigger_offset, agt_entry.data.second_offset, agt_entry.data.addr);

        if (pht_entry) {
            custom_util::SaturatingCounter mode = pht_entry->data.mode;
            auto probs = get_probs(mode);

            std::vector<int> prediction = get_prediction_for_table(table, pht_entry->data.pattern);

            uint64_t insert_probability = probs.first;
            uint64_t delete_probability = probs.second;

            if (is_debug) {
                std::cout << "Table behavior:     " << behavior_to_string(table.behavior) << std::endl;
                std::cout << "Mode:               " << mode.get_cnt() << std::endl;
                std::cout << "Insert probability: " << insert_probability << std::endl;
                std::cout << "Delete probability: " << delete_probability << std::endl;
                std::cout << "Prediction:         " << custom_util::pattern_to_string(prediction) << std::endl;
                std::cout << "Observation:        " << custom_util::pattern_to_string(observation) << std::endl;
            }

            for (int i = 0; i < NUM_BLOCKS; ++i) {
                double rand = random_gen();

                if (prediction[i] && !observation[i]) {
                    if (rand < delete_probability) {
                        prediction[i] = 0;
                    }
                } else if (!prediction[i] && observation[i]) {
                    if (rand < insert_probability) {
                        prediction[i] = PF_FILL_L2;
                    }
                }
            }

            if (is_debug) {
                std::cout << "Updated prediction: " << custom_util::pattern_to_string(prediction) << std::endl;
            }

            std::vector<int> stored_prediction = prediction;
            
            if (touches[idx]) {
                table.update(agt_entry.data.pc, agt_entry.data.trigger_offset, agt_entry.data.second_offset, agt_entry.data.addr, stored_prediction, mode);
            } else {
                table.update_no_touch(agt_entry.data.pc, agt_entry.data.trigger_offset, agt_entry.data.second_offset, agt_entry.data.addr, stored_prediction, mode);
            }
        } else {
            std::vector<int> initial_pattern = get_stored_pattern_for_table(table);

            if (count_bits_set(initial_pattern) > 0) {
                if (is_debug) {
                    std::cout << "Table behavior:      " << behavior_to_string(table.behavior) << std::endl;
                    std::cout << "Update: PHT entry not found, insert new PHT entry" << std::endl;
                    std::cout << "Updated prediction: " << custom_util::pattern_to_string(initial_pattern) << std::endl;
                }

                table.insert(agt_entry.data.pc, agt_entry.data.trigger_offset, agt_entry.data.second_offset, agt_entry.data.addr, initial_pattern);
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

int union_pattern_value(int a, int b) {
    if (a == 0) return b;
    if (b == 0) return a;
    assert(a == b && "Pattern union got conflicting nonzero values");
    return a;
}

std::vector<int> union_patterns(const std::vector<int>& p1, const std::vector<int>& p2) {
    assert(p1.size() == p2.size() && "Patterns must have the same length");

    std::vector<int> result(p1.size(), 0);
    for (size_t i = 0; i < p1.size(); ++i) {
        result[i] = union_pattern_value(p1[i], p2[i]);
    }
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
    std::cout << NAME << " SuperProba NEW NEW prefetcher" << std::endl;

    prefetchers = std::vector<proba::Proba>(NUM_CPUS, proba::Proba(proba::AGT_SIZE, proba::AGT_WAY, proba::FT_SIZE, proba::FT_WAY, proba::PHT_SIZE, proba::PHT_WAY, proba::KEY_WIDTH, proba::JT_SIZE, proba::PB_SIZE, proba::PB_WAY, proba::ACCURACY_THRESHOLD, proba::MARGINAL_ACCURACY_THRESHOLD, proba::DEBUG, cpu));
}

uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, bool useful_prefetch, uint8_t type, uint32_t metadata_in) {
    if (type != LOAD && type != PREFETCH)
        return metadata_in;

    if ((cache_hit && useful_prefetch) || !cache_hit) {
        uint64_t line_addr = (addr >> LOG2_BLOCK_SIZE);
        uint64_t region_num = (addr >> LOG2_PAGE_SIZE);
        int offset = line_addr % proba::NUM_BLOCKS;

        prefetchers[cpu].set_warmup(warmup);

        uint64_t block_num = addr >> LOG2_BLOCK_SIZE;

        prefetchers[cpu].access(block_num, ip, this);
        prefetchers[cpu].prefetch(this, block_num);
    }

    return metadata_in;
}

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    uint64_t evicted_block_num = evicted_addr >> LOG2_BLOCK_SIZE;

    if (evicted_block_num == 0) return metadata_in;
    
    prefetchers[cpu].eviction(evicted_block_num, this);

    return metadata_in;
}

void CACHE::prefetcher_cycle_operate() {}

void CACHE::prefetcher_final_stats() {
    prefetchers[cpu].log();
}
