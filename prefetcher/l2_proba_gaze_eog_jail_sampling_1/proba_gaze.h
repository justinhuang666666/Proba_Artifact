#ifndef PROBA_GAZE_H
#define PROBA_GAZE_H

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

namespace probagaze {

#define __region_offset(block_num) (block_num & REGION_OFFSET_MASK)

#define FT_TYPE custom_util::SRRIPSetAssociativeCache
#define AGT_TYPE custom_util::LRUSetAssociativeCache
#define PHT1_TYPE custom_util::LRUSetAssociativeCache
#define PHT2_TYPE custom_util::LRUSetAssociativeCache
#define PB_TYPE custom_util::LRUSetAssociativeCache

constexpr uint64_t REGION_SIZE = 4 * 1024; // '4KB', '8KB', '16KB, '32KB', '64KB, '128KB', '512KB', '1024KB', '2048KB'
constexpr uint64_t LOG2_REGION_SIZE = champsim::lg2(REGION_SIZE);
constexpr uint64_t REGION_OFFSET_MASK = (1ULL << (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE)) - 1;

constexpr uint64_t IS_DEBUG = true; 

constexpr int NUM_BLOCKS = REGION_SIZE / BLOCK_SIZE;

constexpr int FT_SIZE = 64, FT_WAY = 8;
constexpr int AGT_SIZE = 64, AGT_WAY = 8;

constexpr int PHT1_WAY = 16;
constexpr int PHT1_SIZE = 256;
constexpr int PHT2_WAY = 4;
constexpr int PHT2_SIZE = PHT2_WAY * NUM_BLOCKS;

constexpr int PB_SIZE = 32, PB_WAY = 8;

constexpr int JT_SIZE = 4096;

constexpr int STRIDE_PF_LOOKAHEAD = 2;
constexpr int PF_FILL_L1 = 1;
constexpr int PF_FILL_L2 = 2;
constexpr int PF_FILL_L3 = 3;

// ------------------------- Util Functions ------------------------- //
std::vector<int> pattern_bool2int(std::vector<bool> pattern);
std::vector<int> rotate(const std::vector<int>& pattern, int offset);
uint64_t random_gen();
uint32_t count_bits_set(const std::vector<int> &pattern);
uint32_t count_bits_same(const std::vector<int> &pattern1, const std::vector<int> &pattern2);


// ------------------------- Filter Table ------------------------- //
struct FilterTableData {
    uint64_t trigger_offset;
    uint64_t pc;
};

class FilterTable : public FT_TYPE<FilterTableData> {
    typedef FT_TYPE<FilterTableData> Super;

private:
    uint64_t build_key(uint64_t region_num);
    void write_data(Entry& entry, custom_util::Table& table, int row);

public:
    FilterTable(int size, int num_ways);

    Entry* find(uint64_t region_num);
    Entry insert(uint64_t region_num, uint64_t trigger_offset, uint64_t pc);
    Entry* erase(uint64_t region_num);
    int get_num_valid_entries_per_set(uint64_t region_num);

    std::string log();
};

// ------------------------- Active Generation Table ------------------------- //
struct ActiveGenerationTableData {
    uint64_t trigger_offset;
    uint64_t second_offset;
    uint64_t pc;

    std::vector<bool> pattern;
    std::vector<int> order;
};

class ActiveGenerationTable : public AGT_TYPE<ActiveGenerationTableData> {
    typedef AGT_TYPE<ActiveGenerationTableData> Super;

private:
    void write_data(Entry& entry, custom_util::Table& table, int row);
    uint64_t build_key(uint64_t region_num);

public:
    ActiveGenerationTable(int size, int num_ways);

    Entry* set_pattern(uint64_t region_num, uint64_t offset);

    Entry insert(uint64_t region_num, uint64_t trigger_offset, uint64_t second_offset, uint64_t pc);
    Entry* erase(uint64_t region_num);

    std::string log();
};

// ------------------------- Pattern History Table 1 ------------------------- //
struct PatternHistoryTable1Data {
    std::vector<int> pattern;
    custom_util::SaturatingCounter mode;
};

class PatternHistoryTable1 : public PHT1_TYPE<PatternHistoryTable1Data> {
    typedef PHT1_TYPE<PatternHistoryTable1Data> Super;

private:
    void write_data(Entry& entry, custom_util::Table& table, int row);
    uint64_t build_key(uint64_t pc);

public:
    PatternHistoryTable1(int size, int num_ways);
    void insert(uint64_t pc, const std::vector<int> &pattern); 
    void update(uint64_t pc, const std::vector<int> &pattern, const custom_util::SaturatingCounter &mode);
    Entry* find(uint64_t pc);

    std::string log();
};


// ------------------------- Pattern History Table 2 ------------------------- //
struct PatternHistoryTable2Data {
    std::vector<int> pattern;
    custom_util::SaturatingCounter mode;
};

class PatternHistoryTable2 : public PHT2_TYPE<PatternHistoryTable2Data> {
    typedef PHT2_TYPE<PatternHistoryTable2Data> Super;

private:
    void write_data(Entry& entry, custom_util::Table& table, int row);
    uint64_t build_key(uint64_t trigger, uint64_t second);

public:
    PatternHistoryTable2(int size, int num_ways);

    void insert(uint64_t trigger, uint64_t second, const std::vector<int> &pattern);
    void update(uint64_t trigger, uint64_t second, const std::vector<int> &pattern, const custom_util::SaturatingCounter &mode);
    Entry* find(uint64_t trigger, uint64_t second);

    std::string log();
};

// ------------------------- Prefetch Buffer ------------------------- //
struct PrefetchBufferData {
public:
    std::vector<int> pattern;
    uint64_t trigger;
    uint64_t second;
    std::vector<int> pf_metadata;
};

class PrefetchBuffer : public PB_TYPE<PrefetchBufferData> {
    typedef PB_TYPE<PrefetchBufferData> Super;

private:
    int pattern_len;

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
    
// ------------------------- ProbaGaze Prefetcher ------------------------- //
class ProbaGaze {
private:
    int cpu;

    FilterTable ft;
    ActiveGenerationTable agt;
    PatternHistoryTable1 pht1;
    PatternHistoryTable2 pht2;
    PrefetchBuffer pb;
    JailTable jt;

    bool use_sampling = true;
    bool use_jail_table = true;
    bool use_only_training_on_eog = true;

    bool is_debug;

    void update_in_pht1(const ActiveGenerationTable::Entry& agt_entry, CACHE* cache);
    void update_in_pht2(const ActiveGenerationTable::Entry& agt_entry, CACHE* cache);

    uint64_t sample_rate = 1;
    uint64_t proba_acc_thr1 = 50;
    uint64_t proba_acc_thr2 = 50;

    std::pair<uint64_t,uint64_t> get_probs(custom_util::SaturatingCounter mode);

public:
    int global_level = 0;
    bool warmup;

    ProbaGaze(int ft_size, int ft_ways, int agt_size, int agt_ways, int pht1_size, int pht1_ways, int pht2_size, int pht2_ways, int pb_size, int pb_ways, int jt_size, bool is_debug, int cpu = 0);

    void set_warmup(bool warmup);

    void access(uint64_t block_num, uint64_t ip, CACHE* cache);
    void eviction(uint64_t block_num, CACHE* cache);
    void prefetch(CACHE* cache, uint64_t block_num);



    void log();
};

} // namespace probagaze

#endif