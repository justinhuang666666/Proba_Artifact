#ifndef BINGO_H
#define BINGO_H

/* Bingo [https://mshakerinava.github.io/papers/bingo-hpca19.pdf] */

#include "cache.h"
#include "custom_util.h"

#include <vector>
#include <bits/stdc++.h>
#include <unordered_map>
#include <sstream>
#include <algorithm>
#include <math.h>

namespace bingo_pb {

constexpr int REGION_SIZE = 4 * 1024;
constexpr int LOG2_REGION_SIZE = 12;
constexpr int MIN_ADDR_WIDTH = 6;
constexpr int MAX_ADDR_WIDTH = 16;
constexpr int PC_WIDTH = 16;
constexpr int KEY_WIDTH = 64;
constexpr int PHT_SIZE = 16 * 1024;
constexpr int PHT_WAY = 16;
constexpr int FT_SIZE = 64;
constexpr int FT_WAY = 8;
constexpr int AT_SIZE = 64;
constexpr int AT_WAY = 8;
constexpr int PB_SIZE = 32;
constexpr int PB_WAY = 8;

constexpr double L1D_THRESH = 0.2; 
constexpr double L2C_THRESH = 0.2; 
constexpr double LLC_THRESH = 0.2; 

constexpr int FILL_L1 = 1;
constexpr int FILL_L2 = 2;  
constexpr int FILL_LLC = 3; 

/* PC+Address matches are filled into L1 */
const int PC_ADDRESS_FILL_LEVEL = FILL_L2;

#define __region_offset(block_num) (block_num & REGION_OFFSET_MASK)

constexpr int NUM_BLOCKS = REGION_SIZE / BLOCK_SIZE;
constexpr uint64_t REGION_OFFSET_MASK = (1ULL << (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE)) - 1;

// ------------------------- util functions ------------------------- //
inline std::vector<int> pattern_bool2int(std::vector<bool> pattern) {
    std::vector<int> pattern_int(NUM_BLOCKS, 0);
    for (int i = 0; i < NUM_BLOCKS; i++)
        pattern_int[i] = (pattern[i] ? PC_ADDRESS_FILL_LEVEL : 0);
    return pattern_int;
}

inline uint64_t random_gen() {
    return static_cast<uint64_t>(std::rand() % 100);
}

inline uint32_t count_bits_set(const std::vector<int> &pattern) {
    return std::count(pattern.begin(), pattern.end(), bingo_pb::PC_ADDRESS_FILL_LEVEL);
}

inline uint32_t count_bits_same(const std::vector<int> &pattern1, const std::vector<int> &pattern2) {
    assert(pattern1.size() == pattern2.size() && "Patterns must be the same length");

    uint32_t count = 0;
    for (size_t i = 0; i < pattern1.size(); ++i) {
        if (pattern1[i] == bingo_pb::PC_ADDRESS_FILL_LEVEL && pattern2[i] == bingo_pb::PC_ADDRESS_FILL_LEVEL) {
            ++count;
        }
    }
    return count;
}

class FilterTableData {
public:
    uint64_t pc;
    int offset;
};

class FilterTable : public custom_util::LRUSetAssociativeCache<FilterTableData> {
    typedef custom_util::LRUSetAssociativeCache<FilterTableData> Super;

public:
    FilterTable(int size, int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways, debug_level) {
        // assert(__builtin_popcount(size) == 1);
    }

    Entry* find(uint64_t region_number) {
        uint64_t key = this->build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry) {
            return nullptr;
        }
        Super::rp_promote(key);
        return entry;
    }

    void insert(uint64_t region_number, uint64_t pc, int offset) {
        uint64_t key = this->build_key(region_number);
        // assert(!Super::find(key));
        Super::insert(key, {pc, offset});
        Super::rp_promote(key);
    }

    Entry* erase(uint64_t region_number) {
        uint64_t key = this->build_key(region_number);
        return Super::erase(key);
    }

    std::string log() {
        std::vector<std::string> headers({"Region", "PC", "Offset"});
        return Super::log(headers);
    }

private:
    /* @override */
    void write_data(Entry& entry, custom_util::Table& table, int row) {
        table.set_cell(row, 0, entry.key);
        table.set_cell(row, 1, entry.data.pc);
        table.set_cell(row, 2, entry.data.offset);
    }

    uint64_t build_key(uint64_t region_number) {
        uint64_t key = region_number & ((1ULL << 37) - 1);
        return key;
    }

    /*==========================================================*/
    /* Entry   = [tag, offset, PC, valid, LRU]                  */
    /* Storage = size * (37 - lg(sets) + 5 + 16 + 1 + lg(ways)) */
    /* 64 * (37 - lg(4) + 5 + 16 + 1 + lg(16)) = 488 Bytes      */
    /*==========================================================*/
};

class AccumulationTableData {
public:
    uint64_t pc;
    int offset;
    std::vector<bool> pattern;
};

class AccumulationTable : public custom_util::LRUSetAssociativeCache<AccumulationTableData> {
    typedef custom_util::LRUSetAssociativeCache<AccumulationTableData> Super;

public:
    AccumulationTable(int size, int pattern_len, int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways, debug_level), pattern_len(pattern_len) {
        // assert(__builtin_popcount(size) == 1);
        // assert(__builtin_popcount(pattern_len) == 1);
    }

    /**
     * @return False if the tag wasn't found and true if the pattern bit was successfully set
     */
    bool set_pattern(uint64_t region_number, int offset) {
        uint64_t key = this->build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry) {
            return false;
        }
        entry->data.pattern[offset] = true;
        Super::rp_promote(key);
        return true;
    }

    /* NOTE: `region_number` is probably truncated since it comes from the filter table */
    Entry insert(uint64_t region_number, uint64_t pc, int offset) {
        uint64_t key = this->build_key(region_number);
        // assert(!Super::find(key));
        std::vector<bool> pattern(this->pattern_len, false);
        pattern[offset] = true;
        Entry old_entry = Super::insert(key, {pc, offset, pattern});
        Super::rp_promote(key);
        return old_entry;
    }

    Entry* erase(uint64_t region_number) {
        uint64_t key = this->build_key(region_number);
        return Super::erase(key);
    }

    std::string log() {
        std::vector<std::string> headers({"Region", "PC", "Offset", "Pattern"});
        return Super::log(headers);
    }

private:
    /* @override */
    void write_data(Entry& entry, custom_util::Table& table, int row) {
        table.set_cell(row, 0, entry.key);
        table.set_cell(row, 1, entry.data.pc);
        table.set_cell(row, 2, entry.data.offset);
        table.set_cell(row, 3, custom_util::pattern_to_string(entry.data.pattern));
    }

    uint64_t build_key(uint64_t region_number) {
        uint64_t key = region_number & ((1ULL << 37) - 1);
        return key;
    }

    int pattern_len;

    /*===============================================================*/
    /* Entry   = [tag, map, offset, PC, valid, LRU]                  */
    /* Storage = size * (37 - lg(sets) + 32 + 5 + 16 + 1 + lg(ways)) */
    /* 128 * (37 - lg(8) + 32 + 5 + 16 + 1 + lg(16)) = 1472 Bytes    */
    /*===============================================================*/
};

class PatternHistoryTableData {
public:
    std::vector<int> pattern;
    custom_util::SaturatingCounter mode;
};

class PatternHistoryTable : public custom_util::LRUSetAssociativeCache<PatternHistoryTableData> {
    typedef custom_util::LRUSetAssociativeCache<PatternHistoryTableData> Super;

public:
    PatternHistoryTable(int size, int pattern_len, int min_addr_width, int max_addr_width, int pc_width, int key_width,
                        int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways, debug_level),
        pattern_len(pattern_len), min_addr_width(min_addr_width),
        max_addr_width(max_addr_width), pc_width(pc_width), key_width(key_width) {
    }

    void insert_pc_addr(uint64_t pc, uint64_t address, std::vector<bool> pattern) {
        uint64_t key = this->build_key_pc_addr(pc, address);
        custom_util::SaturatingCounter mode(3,4);
        Super::insert(key, {pattern_bool2int(pattern), mode});
        Super::rp_promote(key);
    }

    void insert_pc_offset(uint64_t pc, uint64_t address, std::vector<bool> pattern) {
        uint64_t key = this->build_key_pc_offset(pc, address);
        custom_util::SaturatingCounter mode(3,4);
        Super::insert(key, {pattern_bool2int(pattern), mode});
        Super::rp_promote(key);
    }

    void update(uint64_t key, std::vector<int> pattern, custom_util::SaturatingCounter mode) {
        Super::update(key, {pattern, mode});
        Super::rp_promote(key);
    }

    PatternHistoryTable::Entry* find_pc_addr(uint64_t pc, uint64_t address){
        uint64_t key = this->build_key_pc_addr(pc, address);
        return Super::find(key);
    }

    PatternHistoryTable::Entry* find_pc_offset(uint64_t pc, uint64_t address){
        uint64_t key = this->build_key_pc_offset(pc, address);
        return Super::find(key);
    }

    std::vector<int> find(uint64_t pc, uint64_t address) {
        uint64_t pc_addr_key = this->build_key_pc_addr(pc, address);
        Entry* pc_addr_entry = Super::find(pc_addr_key);
        if(pc_addr_entry != nullptr) {
            Super::rp_promote(pc_addr_key);
            return pc_addr_entry->data.pattern;
        }
        uint64_t pc_offset_key = this->build_key_pc_offset(pc, address);
        Entry* pc_offset_entry = Super::find(pc_offset_key);
        if(pc_offset_entry != nullptr) {
            Super::rp_promote(pc_offset_key);
            return pc_offset_entry->data.pattern;;
        } else {
            return std::vector<int>{};
        }      
    }

    std::string log() {
        std::vector<std::string> headers({"PC", "Address", "Pattern"});
        return Super::log(headers);
    }

private:
    /* @override */
    void write_data(Entry& entry, custom_util::Table& table, int row) {
        table.set_cell(row, 0, entry.key);
        table.set_cell(row, 1, custom_util::pattern_to_string(entry.data.pattern));
        table.set_cell(row, 2, static_cast<int>(entry.data.mode.get_cnt()));
    }

    static inline uint64_t
    maskN(int n){
        return (static_cast<uint64_t>(1) << n) - 1;
    }

    static inline uint64_t
    hash(uint64_t x) {
        x ^= x>>33;
        x *= 0xff51afd7ed558ccdULL;
        x ^= x>>33;
        x *= 0xc4ceb9fe1a85ec53ULL;
        return x;
    }
    
    uint64_t build_key_pc_addr(uint64_t pc, uint64_t address) {
        const uint64_t key_mask = maskN(this->key_width);
        const uint64_t offset = address & ((1 << this->min_addr_width) - 1);

        const uint64_t h_addr = hash(address);
        const uint64_t h_pc = hash(pc);

        uint64_t mixed = h_addr ^ h_pc;

        return mixed & key_mask;
    }

    uint64_t build_key_pc_offset(uint64_t pc, uint64_t address) {
        const uint64_t key_mask = maskN(this->key_width);
        const uint64_t offset = address & ((1 << this->min_addr_width) - 1);

        const uint64_t h_offset = hash(offset);
        const uint64_t h_pc = hash(pc);

        uint64_t mixed = h_offset ^ h_pc;

        return mixed & key_mask;
    }

    int pattern_len;
    int min_addr_width, max_addr_width, key_width, pc_width;

    /*======================================================*/
    /* Entry   = [tag, map, valid, LRU]                     */
    /* Storage = size * (32 - lg(sets) + 32 + 1 + lg(ways)) */
    /* 8K * (32 - lg(512) + 32 + 1 + lg(16)) = 60K Bytes    */
    /*======================================================*/
};

class PrefetchBufferData {
public:
    std::vector<int> pattern;
};

class PrefetchBuffer : public custom_util::LRUSetAssociativeCache<PrefetchBufferData> {
    typedef custom_util::LRUSetAssociativeCache<PrefetchBufferData> Super;

public:
    PrefetchBuffer(int size, int pattern_len, int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways), pattern_len(pattern_len) {
        if (this->debug_level >= 1)
            std::cerr << "PrefetchBuffer::PrefetchBuffer(size=" << size << ", pattern_len=" << pattern_len
                      << ", debug_level=" << debug_level << ", num_ways=" << num_ways << ")" << std::dec << std::endl;
    }

    void insert(uint64_t region_number, std::vector<int> pattern) {
        if (this->debug_level >= 2)
            std::cerr << "PrefetchBuffer::insert(region_number=0x" << std::hex << region_number
                      << ", pattern=" << custom_util::pattern_to_string(pattern) << ")" << std::dec << std::endl;
        uint64_t key = this->build_key(region_number);
        Super::insert(key, {pattern});
        Super::rp_insert(key);
    }

    int prefetch(CACHE* cache, uint64_t block_num) {
        uint64_t base_addr = block_num << LOG2_BLOCK_SIZE;
        int region_offset = block_num % this->pattern_len;
        uint64_t region_number = block_num / this->pattern_len;
        uint64_t key = this->build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry) {
            return 0;
        }
        Super::rp_promote(key);
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
                        int ok = cache->prefetch_line(0, base_addr, pf_address, pattern[pf_offset] == PC_ADDRESS_FILL_LEVEL, pf_metadata);
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

    std::string log() {
        std::vector<std::string> headers({"Region", "Pattern"});
        return Super::log(headers);
    }

private:
    void write_data(Entry& entry, custom_util::Table& table, int row) {
        table.set_cell(row, 0, entry.key);
        table.set_cell(row, 1, custom_util::pattern_to_string(entry.data.pattern));
    }

    uint64_t build_key(uint64_t region_number) {
        return custom_util::hash_index(region_number, this->index_len);
    }

    int pattern_len;
};

class Bingo {
public:
    Bingo(int pattern_len, int min_addr_width, int max_addr_width, int pc_width, int key_width, int filter_table_size,
          int accumulation_table_size, int pht_size, int pht_ways, int pb_size, int pb_way, int debug_level = 0) :
        pattern_len(pattern_len),
        filter_table(filter_table_size, debug_level),
        accumulation_table(accumulation_table_size, pattern_len, debug_level),
        pht(pht_size, pattern_len, min_addr_width, max_addr_width, pc_width, key_width, debug_level, pht_ways),
        pf_buffer(pb_size, pattern_len, debug_level, pb_way) {}

    void access(uint64_t block_number, uint64_t pc) {
        uint64_t region_number = block_number / this->pattern_len;
        int region_offset = block_number % this->pattern_len;
        bool success = this->accumulation_table.set_pattern(region_number, region_offset);
        if (success)
            return;
        FilterTable::Entry* entry = this->filter_table.find(region_number);
        if (!entry) {
            /* trigger access */
            this->filter_table.insert(region_number, pc, region_offset);
            std::vector<int> pattern = this->find_in_phts(pc, block_number);
            if (pattern.empty())
                return;

            this->pf_buffer.insert(region_number, pattern);
            return;
        }
        if (entry->data.offset != region_offset) {
            /* move from filter table to accumulation table */
            uint64_t region_number = entry->key;
            AccumulationTable::Entry victim = this->accumulation_table.insert(region_number, entry->data.pc, entry->data.offset);
            this->accumulation_table.set_pattern(region_number, region_offset);
            this->filter_table.erase(region_number);
            if (victim.valid) {
                /* move from accumulation table to pattern history table */
                this->update_in_phts(victim);
            }
        }
        return;
    }

    int prefetch(CACHE* cache, uint64_t block_number) {
        int pf_issued = this->pf_buffer.prefetch(cache, block_number);
        return pf_issued;
    }

    void eviction(uint64_t block_number) {
        /* end of generation */
        uint64_t region_number = block_number / this->pattern_len;
        this->filter_table.erase(region_number);
        AccumulationTable::Entry* entry = this->accumulation_table.erase(region_number);
        if (entry) {
            /* move from accumulation table to pattern history table */
            this->update_in_phts(*entry);
        }
    }

    void set_debug_level(int debug_level) { this->debug_level = debug_level; }

    void log() {
        std::cerr << "Filter table begin" << std::dec << std::endl;
        std::cerr << this->filter_table.log();
        std::cerr << "Filter table end" << std::endl;

        std::cerr << "Accumulation table begin" << std::dec << std::endl;
        std::cerr << this->accumulation_table.log();
        std::cerr << "Accumulation table end" << std::endl;

        std::cerr << "PHT table begin" << std::dec << std::endl;
        std::cerr << this->pht.log();
        std::cerr << "PHT table end" << std::endl;

        std::cerr << "Prefetch buffer begin" << std::dec << std::endl;
        std::cerr << this->pf_buffer.log();
        std::cerr << "Prefetch buffer end" << std::endl;
    }

private:
    std::vector<int> find_in_phts(uint64_t pc, uint64_t address) {
        std::vector<int> pattern = this->pht.find(pc,address);
        return pattern;
    }

    std::pair<uint64_t,uint64_t> get_probs(custom_util::SaturatingCounter mode) {
        assert(!(mode.get_cnt() < 0 || mode.get_cnt() > 7));
    
        static constexpr std::array<uint64_t,8> insert_probabilities = {
            1, 5, 10, 40, 100, 100, 100, 100
        };
        static constexpr std::array<uint64_t,8> delete_probabilities = {
            100, 100, 100, 100, 100, 40, 20, 10
        };
        return { insert_probabilities[mode.get_cnt()], delete_probabilities[mode.get_cnt()] };
    }

    void proba_update(PatternHistoryTable::Entry *pht_entry, const std::vector<bool> &pattern){
        const std::vector<int> &observation = pattern_bool2int(pattern);
        std::vector<int> prediction = pht_entry->data.pattern;
        custom_util::SaturatingCounter mode = pht_entry->data.mode;

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

        int64_t local_acc_thr = proba_acc_thr;
        int64_t corrected_accuracy = static_cast<int64_t>(local_accuracy);
        
        local_acc_thr = std::clamp<int64_t>(local_acc_thr, 0, 100);
        corrected_accuracy = std::clamp<int64_t>(corrected_accuracy, 0, 100);

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
            uint64_t rand = random_gen();
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
                    prediction[i] = PC_ADDRESS_FILL_LEVEL;
                }
            }
        }

        pht.update(pht_entry->key, prediction, mode);
    }

    void update_in_phts(const AccumulationTable::Entry &entry) {
        uint64_t pc = entry.data.pc;
        uint64_t address = entry.key * this->pattern_len + entry.data.offset;
        const std::vector<bool> &observation = entry.data.pattern;

        PatternHistoryTable::Entry *pht_pc_addr_entry = this->pht.find_pc_addr(pc, address);
        if(pht_pc_addr_entry){
            this->proba_update(pht_pc_addr_entry, observation);
        } else {
            this->pht.insert_pc_addr(pc, address, observation);
        }

        PatternHistoryTable::Entry *pht_pc_offset_entry = this->pht.find_pc_offset(pc, address);
        if(pht_pc_offset_entry){
            this->proba_update(pht_pc_offset_entry, observation);
        } else {
            this->pht.insert_pc_offset(pc, address, observation);
        }
    }

    int pattern_len;
    FilterTable filter_table;
    AccumulationTable accumulation_table;
    PatternHistoryTable pht;
    PrefetchBuffer pf_buffer;
    int debug_level = 0;

    uint64_t proba_acc_thr = 50;
};


} // namespace bingo_pb
#endif