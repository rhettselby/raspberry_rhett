#include "wav_writer.hpp"

// The 44-byte header of a 16-bit PCM WAV file. Every number is little-endian.
//
//   offset  bytes  contents
//        0      4  "RIFF"
//        4      4  36 + data size (the file size minus these first 8 bytes)
//        8      4  "WAVE"
//       12      4  "fmt " (with a trailing space)
//       16      4  16, the size of the rest of this fmt chunk
//       20      2  1, meaning integer PCM
//       22      2  number of channels
//       24      4  sample rate
//       28      4  byte rate = sample rate * channels * 2
//       32      2  block align = channels * 2 (bytes per frame)
//       34      2  16, the bits per sample
//       36      4  "data"
//       40      4  data size in bytes
//       44         the samples, as int16
//
// You don't know the two sizes (offsets 4 and 40) until you stop writing, so
// write 0 at first and go back to fill them in at the end.

namespace device {

// -----------------------------------------------------------------------------
// Exercise 3, part A: open, write, finish
// -----------------------------------------------------------------------------

WavWriter::WavWriter([[maybe_unused]] const std::filesystem::path& path,
                     [[maybe_unused]] int sample_rate,
                     [[maybe_unused]] int channels) {
    // TODO(you): open the file (throw std::runtime_error if that fails), then
    // write the header.
}

WavWriter::~WavWriter() {
    // TODO(you): if this writer still owns a file, fill in the two sizes. The
    // file itself should close without any code here.
}

void WavWriter::write([[maybe_unused]] std::span<const float> samples) {
    // TODO(you): convert each sample to int16 and append it.
}

// -----------------------------------------------------------------------------
// Exercise 3, part B: moving
// -----------------------------------------------------------------------------

WavWriter::WavWriter([[maybe_unused]] WavWriter&& other) noexcept {
    // TODO(you): take over other's file, and leave `other` owning nothing.
}

WavWriter& WavWriter::operator=([[maybe_unused]] WavWriter&& other) noexcept {
    // TODO(you): careful, *this may already own a file.
    return *this;
}

}  // namespace device
