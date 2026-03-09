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
#define AT_TYPE custom_util::LRUSetAssociativeCache
#define PHT1_TYPE custom_util::LRUSetAssociativeCache
#define PHT2_TYPE custom_util::LRUSetAssociativeCache
#define PB_TYPE custom_util::LRUSetAssociativeCache

constexpr uint64_t REGION_SIZE = 4 * 1024; // '4KB', '8KB', '16KB, '32KB', '64KB, '128KB', '512KB', '1024KB', '2048KB'
constexpr uint64_t LOG2_REGION_SIZE = champsim::lg2(REGION_SIZE);
constexpr uint64_t REGION_OFFSET_MASK = (1ULL << (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE)) - 1;

constexpr int NUM_BLOCKS = REGION_SIZE / BLOCK_SIZE;

constexpr int FT_SIZE = 64, FT_WAY = 8;
constexpr int AT_SIZE = 64, AT_WAY = 8;

constexpr int PHT1_WAY = 16;
constexpr int PHT1_SIZE = 256;
constexpr int PHT2_WAY = 4;
constexpr int PHT2_SIZE = PHT2_WAY * NUM_BLOCKS;

constexpr int PB_SIZE = 32, PB_WAY = 8;

constexpr int STRIDE_PF_LOOKAHEAD = 2;
constexpr int PF_FILL_L1 = 1;
constexpr int PF_FILL_L2 = 2;
constexpr int PF_FILL_L3 = 3;

// ------------------------- Util Functions ------------------------- //
std::vector<int> pattern_bool2int(std::vector<bool> pattern);


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
    void insert(uint64_t region_num, uint64_t trigger_offset, uint64_t pc);
    Entry* erase(uint64_t region_num);

    std::string log();
};

// ------------------------- Accumulate Table ------------------------- //
struct AccumulateTableData {
    uint64_t trigger_offset;
    uint64_t second_offset;
    uint64_t pc;

    std::vector<bool> pattern;
    std::vector<int> order;
};

class AccumulateTable : public AT_TYPE<AccumulateTableData> {
    typedef AT_TYPE<AccumulateTableData> Super;

private:
    void write_data(Entry& entry, custom_util::Table& table, int row);
    uint64_t build_key(uint64_t region_num);

public:
    AccumulateTable(int size, int num_ways);

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

// ------------------------- ProbaGaze Prefetcher ------------------------- //
class ProbaGaze {
private:
    int cpu;

    FilterTable ft;
    AccumulateTable at;
    PatternHistoryTable1 pht1;
    PatternHistoryTable2 pht2;
    PrefetchBuffer pb;

    void update_in_pht1(const AccumulateTable::Entry& agt_entry);
    void update_in_pht2(const AccumulateTable::Entry& agt_entry);

public:
    int global_level = 0;
    bool warmup;

    ProbaGaze(int ft_size, int ft_ways, int at_size, int at_ways, int pht1_size, int pht1_ways, int pht2_size, int pht2_ways, int pb_size, int pb_ways, int cpu);
    ProbaGaze();
    void set_warmup(bool warmup);

    void access(uint64_t block_num, uint64_t ip, CACHE* cache);
    void eviction(uint64_t block_num);
    void prefetch(CACHE* cache, uint64_t block_num);

    void log();
};

} // namespace probagaze

#endif