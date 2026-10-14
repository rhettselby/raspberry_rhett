// noise_gen: writes a few seconds of white, pink or brown noise to a WAV file.
//
//   ./device/build/noise_gen pink 10 pink.wav
//   afplay pink.wav          # listen on the Mac (turn the volume down first)
//
// It only calls your code in noise.cpp and wav_writer.cpp, so it starts
// working once exercises 1 to 3 are done.

#include "noise.hpp"
#include "wav_writer.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <optional>
#include <random>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace {

constexpr int kSampleRate = 48000;
constexpr std::size_t kBlockSize = 1024;  // samples generated and written per loop

std::optional<device::NoiseColor> parse_color(std::string_view name) {
    if (name == "white") return device::NoiseColor::White;
    if (name == "pink") return device::NoiseColor::Pink;
    if (name == "brown") return device::NoiseColor::Brown;
    return std::nullopt;
}

int usage() {
    std::cerr << "usage: noise_gen <white|pink|brown> <seconds> <output.wav>\n";
    return EXIT_FAILURE;
}

}  // namespace

int main(int argc, char* argv[]) {
    if (argc != 4) return usage();
    const auto color = parse_color(argv[1]);
    if (!color) return usage();

    try {
        const int seconds = std::stoi(argv[2]);
        if (seconds <= 0) return usage();
        const std::string path = argv[3];

        // A different seed each run, so no two files are identical.
        const auto noise = device::make_noise(*color, std::random_device{}());
        if (!noise) {
            std::cerr << "noise_gen: make_noise() returned nullptr; finish exercise 2 first\n";
            return EXIT_FAILURE;
        }

        device::WavWriter wav(path, kSampleRate, 1);
        std::vector<float> block(kBlockSize);
        std::size_t remaining = static_cast<std::size_t>(seconds) * kSampleRate;
        while (remaining > 0) {
            const auto chunk = std::span(block).first(std::min(remaining, kBlockSize));
            noise->fill(chunk);
            wav.write(chunk);
            remaining -= chunk.size();
        }
        std::cout << "wrote " << seconds << " s of " << argv[1] << " noise to " << path << '\n';
    } catch (const std::exception& e) {
        // std::stoi throws for "abc"; WavWriter throws if the file can't be opened.
        std::cerr << "noise_gen: " << e.what() << '\n';
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
