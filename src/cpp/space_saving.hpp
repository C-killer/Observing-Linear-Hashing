#pragma once
#include <cstdint>
#include <unordered_map>
#include <vector>
#include <queue>
#include <utility>
#include <limits>
#include <algorithm>   // push_heap/pop_heap

// Space-Saving / Frequent algorithm with lazy min-heap
class SpaceSaving {
public:
    struct Entry {
        uint32_t c;   // count estimate
        uint32_t e;   // error
        uint32_t ver; // version for lazy heap validity
    };

    explicit SpaceSaving(size_t k) : k_(k) {
        table_.reserve(k);
        heap_.reserve(k * 2);
    }

    void offer(uint64_t key) {
        if (k_ == 0) return;

        auto it = table_.find(key);
        if (it != table_.end()) {
            // increment existing
            it->second.c += 1;
            it->second.ver += 1;
            heap_.push_back(Node{it->second.c, key, it->second.ver});
            std::push_heap(heap_.begin(), heap_.end(), greaterNode);
            if (it->second.c > max_c_) max_c_ = it->second.c;
            return;
        }

        if (table_.size() < k_) {
            // insert new
            Entry ent{1, 0, 1};
            table_.emplace(key, ent);
            heap_.push_back(Node{1, key, 1});
            std::push_heap(heap_.begin(), heap_.end(), greaterNode);
            if (max_c_ < 1) max_c_ = 1;
            return;
        }

        // table full: replace current min valid
        auto [cmin, ymin] = pop_min_valid();

        // remove ymin
        table_.erase(ymin);

        // insert key with c = cmin+1, e = cmin
        Entry ent{uint32_t(cmin + 1), uint32_t(cmin), 1};
        table_.emplace(key, ent);
        heap_.push_back(Node{ent.c, key, ent.ver});
        std::push_heap(heap_.begin(), heap_.end(), greaterNode);
        if (ent.c > max_c_) max_c_ = ent.c;
    }

    uint32_t max_count() const { return max_c_; }

private:
    struct Node {
        uint32_t c;
        uint64_t key;
        uint32_t ver;
    };

    static bool greaterNode(const Node& a, const Node& b) {
        // min-heap behavior using push_heap/pop_heap with "greater" comparator
        // Actually push_heap/pop_heap expect "less" for max-heap. We invert by comparing (a.c > b.c).
        // We'll use (a.c > b.c) so the smallest c bubbles to front when used with pop_heap + this comparator.
        if (a.c != b.c) return a.c > b.c;
        return a.key > b.key;
    }

    std::pair<uint32_t, uint64_t> pop_min_valid() {
        // pop until valid: node matches current table entry's (c, ver)
        while (true) {
            std::pop_heap(heap_.begin(), heap_.end(), greaterNode);
            Node nd = heap_.back();
            heap_.pop_back();

            auto it = table_.find(nd.key);
            if (it != table_.end()) {
                const Entry& cur = it->second;
                if (cur.c == nd.c && cur.ver == nd.ver) {
                    return {nd.c, nd.key};
                }
            }
            // else stale -> continue
        }
    }

private:
    size_t k_;
    std::unordered_map<uint64_t, Entry> table_;
    std::vector<Node> heap_;
    uint32_t max_c_ = 0;
};
