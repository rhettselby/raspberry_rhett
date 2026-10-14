#include "noise.hpp"
namespace device {

// NoiseSource::fill and WhiteNoise

void NoiseSource::fill(std::span<float> out) {
    for (auto& n : out){
        n = next();
    }
}

WhiteNoise::WhiteNoise([[maybe_unused]] std::uint32_t seed) : dist_(-1.0f, 1.0f), engine_(seed) {

}

float WhiteNoise::next() {
    
    float res = dist_(engine_);
    return res;
}


// make_noise

std::unique_ptr<NoiseSource> make_noise(NoiseColor color, std::uint32_t seed) {
    switch(color){
        case NoiseColor::White:
            return std::make_unique<WhiteNoise>(seed);
        
        case NoiseColor::Brown:
            return std::make_unique<BrownNoise>(seed);
        
        case NoiseColor::Pink:
            return std::make_unique<PinkNoise>(seed);
    }

    throw std::invalid_argument("unknown NoiseColor");

}
// BrownNoise

BrownNoise::BrownNoise(std::uint32_t seed) : white_(seed), level_(0.0f)  {}
const float leak = .98f;
float BrownNoise::next() {
    float white = white_.next();
    level_ = leak * level_ + (1 - leak) * white;
    return std::clamp(level_ * 3.5f, -1.0f, 1.0f);
}


// PinkNoise

PinkNoise::PinkNoise(std::uint32_t seed) : white_(seed), levels_{} {}

float PinkNoise::next() {
    const std::array<float, 6> leaks = {0.99886f, 0.99332f, 0.96900f, 0.86650f, 0.55000f, -0.7616f};
    const std::array<float, 6> gains = {0.0555179f, 0.0750759f, 0.1538520f, 0.3104856f, 0.5329522f, -0.0168980f};
    float white = white_.next();
    float pink = 0;
    for (std::size_t i = 0; i < 6; i++){
        levels_[i] = leaks[i] * levels_[i] + gains[i] * white;
        pink = pink + levels_[i];
    }
    pink = pink + levels_[6] + white * .5362f;
    levels_[6] = white * 0.115926f;
    return std::clamp(pink * 0.11f, -1.0f, 1.0f);
}

} 
