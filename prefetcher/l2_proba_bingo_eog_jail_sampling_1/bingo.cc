/* Bingo */
#include "cache.h"
#include <bits/stdc++.h>
#include "custom_util.h"
#include "bingo.h"

/* Bingo settings */
namespace {

std::vector<bingo_pb::Bingo> prefetchers;

/* stats */
std::unordered_set<uint64_t> prefetched_blocks[NUM_CPUS];

uint64_t roi_prefetch_cnt[NUM_CPUS][2] = {0};
uint64_t roi_cover_cnt[NUM_CPUS][2] = {0};
uint64_t roi_overpredict_cnt[NUM_CPUS][2] = {0};
} // namespace

void CACHE::prefetcher_initialize() {
    std::cout << NAME << " Bingo with PrefetchBuffer prefetcher" << std::endl;

    prefetchers = std::vector<bingo_pb::Bingo>(NUM_CPUS, bingo_pb::Bingo(bingo_pb::REGION_SIZE >> LOG2_BLOCK_SIZE, bingo_pb::MIN_ADDR_WIDTH, bingo_pb::MAX_ADDR_WIDTH, bingo_pb::KEY_WIDTH, bingo_pb::FT_SIZE, bingo_pb::FT_WAY, bingo_pb::AT_SIZE, bingo_pb::AT_WAY, bingo_pb::PHT_SIZE, bingo_pb::PHT_WAY, bingo_pb::JT_SIZE, bingo_pb::PB_SIZE, bingo_pb::PB_WAY, 0));
}

uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint32_t metadata_in) {
    if (type != LOAD && type != PREFETCH)
        return metadata_in;

    uint64_t block_number = addr >> LOG2_BLOCK_SIZE;

    /* call prefetcher and send prefetches */
    prefetchers[cpu].access(block_number, ip);

    prefetchers[cpu].prefetch(this, block_number);

    return metadata_in;
}

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    uint64_t evicted_block_number = evicted_addr >> LOG2_BLOCK_SIZE;

    prefetchers[cpu].eviction(evicted_block_number);

    return metadata_in;
}

void CACHE::prefetcher_cycle_operate() {}

void CACHE::prefetcher_final_stats() {
    prefetchers[cpu].log();
}
