#include "trial_maxload.hpp"
#include "linear_hash.hpp"
#include "space_saving.hpp"
#include "samplers.hpp"

#include <random>
#include <vector>
#include <stdexcept>

// 因为SpaceSaving的key类型是uint64_t，但h(x)的输出是l位，当l>64时会跨多个block存储。
// 需要压缩的根本原因是这两者之间的不匹配：
//      h(x) 输出: [block0][block1][block2]...  ← l=200时有4个uint64
//      SpaceSaving.offer(key)                  ← 只接受一个uint64
// 在之前的python实现中，h(x) 输出: [block0][block1][block2]... 是一串bits，我们可以直接用其表示的整数当key
// 而这里我们通过fingerprint64，近似实现了: 相同的y产生相同的key，不同的y产生不同的key
static inline uint64_t fingerprint64(const std::vector<uint64_t>& y) {
    // 任意长度 uint64 数组 ==> uint64 
    uint64_t h = 0x9e3779b97f4a7c15ULL;
    for (uint64_t v : y) {
        // SplitMix64混淆 --> 让输入的每一个bit都影响输出的所有bit
        v ^= v >> 30;  // 高位的信息混入低位
        v *= 0xbf58476d1ce4e5b9ULL;    // v *= 大质数：乘法让每个bit扩散到更高位（进位传播）
        v ^= v >> 27; v *= 0x94d049bb133111ebULL;
        v ^= v >> 31;
        // 把多个64位值合并进一个h，且顺序敏感; 让 h 自身的历史状态参与混合，使得 [a,b] 和 [b,a] 得到不同结果
        h ^= v + 0x9e3779b97f4a7c15ULL + (h<<6) + (h>>2);
    }
    return h;
}

int run_trial_maxload(const TrialConfig& cfg) {
    if (cfg.u <= 0 || cfg.l <= 0 || cfg.m < 0) throw std::invalid_argument("bad cfg");
    if (cfg.k <= 0) return 0;

    LinearHash h(cfg.l, cfg.u, cfg.seed_h);

    const int B = (cfg.u + 63) / 64;
    std::vector<uint64_t> x_blocks(B);

    std::mt19937_64 rngS(cfg.seed_S);
    DistSpec dist{cfg.dist};

    SpaceSaving ss(size_t(cfg.k));

    for (int64_t i = 0; i < cfg.m; ++i) {
        sample_blocks(rngS, x_blocks, cfg.u, dist);
        auto y_blocks = h.hash(x_blocks);          // l=500 -> ~8 blocks
        uint64_t key = fingerprint64(y_blocks);
        ss.offer(key);
    }
    return int(ss.max_count());
}
