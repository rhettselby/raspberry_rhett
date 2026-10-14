// Writes audio to a .wav file as 16-bit PCM, so you can listen to the noise
// generators and plot their spectrum.
//
// This is the project's first RAII wrapper around a C API: a WavWriter owns a
// FILE* from <cstdio>, the same way the ALSA output will later own a
// snd_pcm_t*. Exercise 3 in device/README.md.
#pragma once

#include <cstdio>
#include <filesystem>
#include <memory>
#include <span>

namespace device {

class WavWriter {
public:
    // Opens (creating or truncating) `path` and writes a WAV header whose size
    // fields are left as 0 for now. Throws std::runtime_error if the file
    // can't be opened.
    WavWriter(const std::filesystem::path& path, int sample_rate, int channels);

    // Fills in the real sizes in the header, then closes the file.
    ~WavWriter();

    // A WavWriter owns its file, so a copy makes no sense: two objects would
    // both try to finish and close the same FILE*. Copying is deleted...
    WavWriter(const WavWriter&) = delete;
    WavWriter& operator=(const WavWriter&) = delete;

    // ...but the file can be handed over to another WavWriter. Exercise 3B.
    WavWriter(WavWriter&& other) noexcept;
    WavWriter& operator=(WavWriter&& other) noexcept;

    // Appends samples. Each float becomes a 16-bit integer: values are clamped
    // to [-1, 1], multiplied by 32767 and rounded. Stereo samples are
    // interleaved: left, right, left, right...
    void write(std::span<const float> samples);

private:
    // TODO(you), exercise 3: the file, plus whatever you need to fill in the
    // header when you're done.
};

}  // namespace device
