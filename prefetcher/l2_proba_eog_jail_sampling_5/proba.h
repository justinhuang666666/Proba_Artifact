#ifndef PROBA_H
#define PROBA_H

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

#include "custom_util.h"
#include "cache.h"

#include <stdint.h>
#include <random>
#include <deque>

namespace proba {

#define __region_offset(block_num) (block_num & REGION_OFFSET_MASK)

#define AGT_TYPE custom_util::RandomSetAssociativeCache
#define PHT_TYPE custom_util::LRUSetAssociativeCache
#define PB_TYPE custom_util::LRUSetAssociativeCache

constexpr uint64_t REGION_SIZE = 4 * 1024; // '4KB', '8KB', '16KB, '32KB', '64KB, '128KB', '512KB', '1024KB', '2048KB'
constexpr uint64_t LOG2_REGION_SIZE = champsim::lg2(REGION_SIZE);
constexpr uint64_t REGION_OFFSET_MASK = (1ULL << (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE)) - 1;
constexpr bool DEBUG = false;

constexpr int NUM_BLOCKS = REGION_SIZE / BLOCK_SIZE;

constexpr int AGT_SIZE = 64, AGT_WAY = 8;
constexpr int PHT_WAY = 16;
constexpr int PHT_SIZE = 256;
constexpr int PB_SIZE = 32, PB_WAY = 8;


constexpr int JT_SIZE = 4096;

constexpr int PF_FILL_L1 = 1;
constexpr int PF_FILL_L2 = 2;
constexpr int PF_FILL_L3 = 3;

// ------------------------- Util Functions ------------------------- //
std::vector<int> pattern_bool2int(std::vector<bool> pattern);
std::vector<int> rotate(const std::vector<int>& pattern, int offset);
uint64_t random_gen();
uint32_t count_bits_set(const std::vector<int> &pattern);
uint32_t count_bits_same(const std::vector<int> &pattern1, const std::vector<int> &pattern2);

// ------------------------- Active Generation Table ------------------------- //
struct ActiveGenerationTableData {
    uint64_t trigger_offset;
    uint64_t pc;
    std::vector<bool> pattern;
};

class ActiveGenerationTable : public AGT_TYPE<ActiveGenerationTableData> {
    typedef AGT_TYPE<ActiveGenerationTableData> Super;

private:
    void write_data(Entry& entry, custom_util::Table& table, int row);
    uint64_t build_key(uint64_t region_num);

public:
    ActiveGenerationTable(int size, int num_ways);

    Entry* set_pattern(uint64_t region_num, uint64_t offset);

    Entry insert(uint64_t region_num, uint64_t trigger_offset, uint64_t pc);
    Entry* erase(uint64_t region_num);
    int get_num_valid_entries_per_set(uint64_t region_num);

    std::string log();
};

// ------------------------- Pattern History Table ------------------------- //
struct PatternHistoryTableData {
    std::vector<int> pattern;
    custom_util::SaturatingCounter mode;
};

class PatternHistoryTable : public PHT_TYPE<PatternHistoryTableData> {
    typedef PHT_TYPE<PatternHistoryTableData> Super;

private:
    void write_data(Entry& entry, custom_util::Table& table, int row);
    uint64_t build_key(uint64_t pc);

public:
    PatternHistoryTable(int size, int num_ways);
    void insert(uint64_t pc, const std::vector<int> &pattern); 
    void update(uint64_t pc, const std::vector<int> &pattern, const custom_util::SaturatingCounter &mode);
    Entry* find(uint64_t pc);

    std::string log();
};

// ------------------------- Prefetch Buffer ------------------------- //
struct PrefetchBufferData {
public:
    std::vector<int> pattern;
};

class PrefetchBuffer : public PB_TYPE<PrefetchBufferData> {
    typedef PB_TYPE<PrefetchBufferData> Super;

private:
    int pattern_len;
    int debug_level;

    void write_data(Entry& entry, custom_util::Table& table, int row);
    uint64_t build_key(uint64_t region_num);

public:
    bool warmup;

    PrefetchBuffer(int size, int pattern_len, int debug_level, int num_ways);
    void insert(uint64_t region_num, std::vector<int> pattern);
    int prefetch(CACHE* cache, uint64_t block_num);

    std::string log();
};

// ------------------------- Jail Table ------------------------- //
class JailTable {
private:
    const int num_entries;
    const int mask;

    std::vector<bool> jail_table1;
    std::vector<bool> jail_table2;

    // Hash/folding for region base, then map to table index.
    uint64_t hash(uint64_t key) const noexcept {
        uint64_t x = static_cast<uint64_t>(key);
        // Simple xorshift-style mixing
        x ^= x >> 33;
        x ^= x >> 17;
        x ^= x >> 9;

        return static_cast<uint64_t>(x) & mask;
    }

    uint64_t build_key(uint64_t region_num) {
        uint64_t key = region_num & ((1ULL << 37) - 1);
        // return custom_util::hash_index(key, this->index_len);
        return key;
    }

public:
    JailTable(int num_entries) : num_entries(num_entries), mask(num_entries - 1), jail_table1(num_entries, false), jail_table2(num_entries, false) {
        assert(custom_util::is_pow2(num_entries));
    }

    void mark(uint64_t region_num) {
        uint64_t key = build_key(region_num);
        jail_table1[hash(key)] = true;
        jail_table2[hash(key*1664525+1013904223)] = true;
    }

    // Clear the jail bit for a region (released).
    void unmark(uint64_t region_num) {
        uint64_t key = build_key(region_num);
        jail_table1[hash(key)] = false;
        jail_table2[hash(key*1664525+1013904223)] = false;
    }

    // Query whether a region is currently jailed.
    bool in_jail(uint64_t region_num) {
        uint64_t key = build_key(region_num);
        return (jail_table1[hash(key)]&&jail_table2[hash(key*1664525+1013904223)]);
    }
};

// ------------------------- Proba Prefetcher ------------------------- //
class Proba {
private:
    ActiveGenerationTable agt;
    PatternHistoryTable pht;
    JailTable jt;
    PrefetchBuffer pb;

    int sample_rate = 5;
    int proba_acc_thr = 50;

    int ewma_window_size = 1000;
    int ewma_alpha_num = 1;
    int ewma_alpha_den = 2;

    bool is_accuracy_targeter = false;
    bool is_accuracy_correction = false;

    uint64_t num_valid_update = 0;
    uint64_t total_num_valid_update = 0;

    uint64_t global_accurate_pf_sum = 0;
    uint64_t global_pf_sum = 0;
    uint64_t ewma_accuracy_estimate = 0;
    uint64_t ewma_global_accuracy = 0;

    uint64_t prev_pf_useful = 0;
    uint64_t prev_pf_unused = 0;

    bool use_sampling = true;
    bool use_jail_table = true;
    bool use_only_training_on_eog = true;

    bool is_debug;

    int cpu;

    void update_in_pht(const ActiveGenerationTable::Entry& agt_entry, bool is_end_of_generation, CACHE* cache);

public:
    int global_level = 0;
    bool warmup;

    Proba(int agt_size, int agt_ways, int pht_size, int pht_ways, int jt_size, int pb_size, int pb_ways, bool is_debug, int cpu);

    void set_warmup(bool warmup);

    void ewma_update(uint64_t& ewma, uint64_t sample, int alpha_num, int alpha_den);
    std::pair<uint64_t,uint64_t> get_probs(custom_util::SaturatingCounter mode);

    void access(uint64_t block_num, uint64_t pc, CACHE* cache);
    void eviction(uint64_t block_num, CACHE* cache);
    int prefetch(CACHE* cache, uint64_t block_num);

    void log();
};

} // namespace proba

#endif