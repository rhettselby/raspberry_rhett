// Noise generators: white, pink and brown noise as mono float samples in [-1, 1].
#pragma once

#include <cstdint>
#include <memory>
#include <random> 
#include <span>

namespace device {

// Anything that produces a stream of mono samples in [-1, 1].
// This is an abstract base class: you can't create a NoiseSource itself, only
// the classes derived from it. Code that just needs "some noise" can hold a
// NoiseSource& or a std::unique_ptr<NoiseSource> without knowing the color.
class NoiseSource {
public:
    // A base class with virtual functions needs a virtual destructor, so that
    // deleting a WhiteNoise through a NoiseSource* also runs ~WhiteNoise().
    virtual ~NoiseSource() = default;

    // Returns the next sample. "= 0" makes it pure virtual: every derived
    // class must override it.
    virtual float next() = 0;

    // Fills every element of `out` with the next samples, in order. It isn't
    // virtual because it works the same way for every color. Exercise 1.
    void fill(std::span<float> out);
};

// White noise: every sample is independent and uniformly distributed, so all
// frequencies have equal power. Its spectrum is flat: 0 dB per octave.
class WhiteNoise : public NoiseSource {
public:
    // The same seed always gives the same samples, which keeps tests repeatable.
    // `explicit` stops an integer from silently converting into a WhiteNoise.
    explicit WhiteNoise(std::uint32_t seed);
    float next() override;

private:
    std::mt19937 engine_;
    std::uniform_real_distribution<float> dist_;
};

// Brown noise: a running sum of white noise, so each sample stays close to the
// one before it. Power falls by 6 dB per octave: a deep rumble.
class BrownNoise : public NoiseSource {
public:
    explicit BrownNoise(std::uint32_t seed);
    float next() override;

private:
    WhiteNoise white_;
    float level_;
};

// Pink noise: between white and brown. Power falls by 3 dB per octave, so
// every octave carries the same energy. It sounds like steady rain.
class PinkNoise : public NoiseSource {
public:
    explicit PinkNoise(std::uint32_t seed);
    float next() override;

private:
    WhiteNoise white_;
    std::array<float, 7> levels_; //Use array over vector when known/fixed size
};

enum class NoiseColor { White, Pink, Brown };

// Creates a generator of the given color. Exercise 2.
std::unique_ptr<NoiseSource> make_noise(NoiseColor color, std::uint32_t seed);

}  // namespace device
