// Tests for noise.hpp. Each TEST checks one small fact about a generator. They
// all fail at first and pass, group by group, as you finish the exercises.
//
// Run one group:  ctest --test-dir device/build -R WhiteNoise --output-on-failure

#include "noise.hpp"

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <span>
#include <vector>

namespace device {
namespace {

// About 22 seconds at 48 kHz: enough samples for the statistics to be stable.
constexpr std::size_t kNumSamples = 1 << 20;

constexpr const char* kSilent = "every sample is 0: next() isn't implemented yet";

std::vector<float> generate(NoiseSource& source, std::size_t count = kNumSamples) {
    std::vector<float> samples(count);
    source.fill(samples);
    return samples;
}

double mean(std::span<const float> samples) {
    double sum = 0.0;
    for (float s : samples) {
        sum += s;
    }
    return sum / static_cast<double>(samples.size());
}

double rms(std::span<const float> samples) {
    double sum = 0.0;
    for (float s : samples) {
        sum += static_cast<double>(s) * s;
    }
    return std::sqrt(sum / static_cast<double>(samples.size()));
}

// How much each sample resembles the one before it, from -1 to 1. White noise
// scores about 0 because its samples are independent; brown noise wanders
// slowly and scores close to 1. It's a cheap stand-in for a spectrum.
double lag1_autocorrelation(std::span<const float> samples) {
    const double m = mean(samples);
    double numerator = 0.0;
    double denominator = 0.0;
    for (std::size_t i = 0; i < samples.size(); ++i) {
        const double centered = samples[i] - m;
        denominator += centered * centered;
        if (i + 1 < samples.size()) {
            numerator += centered * (samples[i + 1] - m);
        }
    }
    return numerator / denominator;
}

void expect_in_range(std::span<const float> samples) {
    const auto [lowest, highest] = std::minmax_element(samples.begin(), samples.end());
    EXPECT_GE(*lowest, -1.0f);
    EXPECT_LE(*highest, 1.0f);
}

// -----------------------------------------------------------------------------
// Exercise 1: NoiseSource::fill and WhiteNoise
// -----------------------------------------------------------------------------

TEST(WhiteNoise, FillWritesEverySample) {
    WhiteNoise noise(1);
    std::vector<float> samples(1000, 42.0f);  // 42 can't come from noise in [-1, 1]
    noise.fill(samples);
    EXPECT_EQ(std::count(samples.begin(), samples.end(), 42.0f), 0)
        << "fill() left some samples untouched";
}

TEST(WhiteNoise, IsNotSilent) {
    WhiteNoise noise(1);
    // Uniform noise in [-1, 1] has an RMS level of 1/sqrt(3), about 0.58.
    EXPECT_GT(rms(generate(noise)), 0.3);
}

TEST(WhiteNoise, SamplesAreInRange) {
    WhiteNoise noise(1);
    const auto samples = generate(noise);
    ASSERT_GT(rms(samples), 0.0) << kSilent;
    expect_in_range(samples);
}

TEST(WhiteNoise, AveragesToZero) {
    WhiteNoise noise(1);
    const auto samples = generate(noise);
    ASSERT_GT(rms(samples), 0.0) << kSilent;
    EXPECT_NEAR(mean(samples), 0.0, 0.01);
}

TEST(WhiteNoise, SameSeedGivesSameSamples) {
    WhiteNoise a(7);
    WhiteNoise b(7);
    const auto from_a = generate(a, 1000);
    ASSERT_GT(rms(from_a), 0.0) << kSilent;
    EXPECT_TRUE(from_a == generate(b, 1000));
}

TEST(WhiteNoise, DifferentSeedsGiveDifferentSamples) {
    WhiteNoise a(7);
    WhiteNoise b(8);
    EXPECT_FALSE(generate(a, 1000) == generate(b, 1000));
}

TEST(WhiteNoise, NeighboringSamplesAreUnrelated) {
    WhiteNoise noise(1);
    const auto samples = generate(noise);
    ASSERT_GT(rms(samples), 0.0) << kSilent;
    EXPECT_NEAR(lag1_autocorrelation(samples), 0.0, 0.01);
}

// -----------------------------------------------------------------------------
// Exercise 2: make_noise
// -----------------------------------------------------------------------------

TEST(MakeNoise, CreatesTheRequestedColor) {
    // dynamic_cast gives nullptr if the object isn't really of that type.
    const auto white = make_noise(NoiseColor::White, 1);
    const auto pink = make_noise(NoiseColor::Pink, 1);
    const auto brown = make_noise(NoiseColor::Brown, 1);
    EXPECT_NE(dynamic_cast<WhiteNoise*>(white.get()), nullptr);
    EXPECT_NE(dynamic_cast<PinkNoise*>(pink.get()), nullptr);
    EXPECT_NE(dynamic_cast<BrownNoise*>(brown.get()), nullptr);
}

TEST(MakeNoise, PassesTheSeedOn) {
    const auto made = make_noise(NoiseColor::White, 7);
    ASSERT_NE(made, nullptr);
    WhiteNoise direct(7);
    const auto from_direct = generate(direct, 1000);
    ASSERT_GT(rms(from_direct), 0.0) << kSilent;
    EXPECT_TRUE(generate(*made, 1000) == from_direct);
}

// -----------------------------------------------------------------------------
// Exercise 4: BrownNoise
// -----------------------------------------------------------------------------

TEST(BrownNoise, IsNotSilent) {
    BrownNoise noise(1);
    EXPECT_GT(rms(generate(noise)), 0.05) << "too quiet: scale the output up";
}

TEST(BrownNoise, SamplesAreInRange) {
    BrownNoise noise(1);
    const auto samples = generate(noise);
    ASSERT_GT(rms(samples), 0.0) << kSilent;
    expect_in_range(samples);
}

TEST(BrownNoise, SameSeedGivesSameSamples) {
    BrownNoise a(7);
    BrownNoise b(7);
    const auto from_a = generate(a, 1000);
    ASSERT_GT(rms(from_a), 0.0) << kSilent;
    EXPECT_TRUE(from_a == generate(b, 1000));
}

TEST(BrownNoise, NeighboringSamplesAreClose) {
    BrownNoise noise(1);
    const auto samples = generate(noise);
    ASSERT_GT(rms(samples), 0.0) << kSilent;
    EXPECT_GT(lag1_autocorrelation(samples), 0.9);
}

TEST(BrownNoise, DoesNotDrift) {
    // A plain running sum of white noise is a random walk: it wanders away from
    // 0 and gets stuck at the edges of [-1, 1]. With a leak, every second of
    // output averages near 0 and hardly any samples sit at the edges.
    BrownNoise noise(1);
    const auto samples = generate(noise);
    ASSERT_GT(rms(samples), 0.0) << kSilent;

    constexpr std::size_t kOneSecond = 48000;
    const std::span<const float> all(samples);
    double worst = 0.0;
    for (std::size_t start = 0; start + kOneSecond <= all.size(); start += kOneSecond) {
        worst = std::max(worst, std::abs(mean(all.subspan(start, kOneSecond))));
    }
    EXPECT_LT(worst, 0.25) << "the output drifts away from 0: add a leak";

    const auto at_edges = std::count_if(samples.begin(), samples.end(),
                                        [](float s) { return std::abs(s) >= 0.999f; });
    EXPECT_LT(static_cast<double>(at_edges) / static_cast<double>(samples.size()), 0.01)
        << "over 1% of samples are stuck at -1 or 1: add a leak, or scale the output down";
}

// -----------------------------------------------------------------------------
// Exercise 5: PinkNoise
// -----------------------------------------------------------------------------

TEST(PinkNoise, IsNotSilent) {
    PinkNoise noise(1);
    EXPECT_GT(rms(generate(noise)), 0.05) << "too quiet: scale the output up";
}

TEST(PinkNoise, SamplesAreInRange) {
    PinkNoise noise(1);
    const auto samples = generate(noise);
    ASSERT_GT(rms(samples), 0.0) << kSilent;
    expect_in_range(samples);
}

TEST(PinkNoise, AveragesToZero) {
    PinkNoise noise(1);
    const auto samples = generate(noise);
    ASSERT_GT(rms(samples), 0.0) << kSilent;
    EXPECT_NEAR(mean(samples), 0.0, 0.05);
}

TEST(PinkNoise, SameSeedGivesSameSamples) {
    PinkNoise a(7);
    PinkNoise b(7);
    const auto from_a = generate(a, 1000);
    ASSERT_GT(rms(from_a), 0.0) << kSilent;
    EXPECT_TRUE(from_a == generate(b, 1000));
}

TEST(PinkNoise, IsBetweenWhiteAndBrown) {
    // White scores about 0 here and brown above 0.9; pink lands in between.
    PinkNoise noise(1);
    const auto samples = generate(noise);
    ASSERT_GT(rms(samples), 0.0) << kSilent;
    const double correlation = lag1_autocorrelation(samples);
    EXPECT_GT(correlation, 0.3) << "too close to white noise";
    EXPECT_LT(correlation, 0.95) << "too close to brown noise";
}

}  // namespace
}  // namespace device
