#include "wav_writer.hpp"

#include <bit>
#include <cstdint>
#include <stdexcept>
#include <string>

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
namespace {

// write_le writes a value's bytes in memory order, which is only correct
// because both the Mac and the Pi store numbers little-endian, like WAV does.
static_assert(std::endian::native == std::endian::little);

// Writes `value` as raw bytes. Its type decides how many: 2 for a
// std::uint16_t, 4 for a std::uint32_t. Name the type at each call.
template <typename T>
void write_le(std::FILE* f, T value) {
    std::fwrite(&value, sizeof value, 1, f);
}

// Writes a 4-character chunk name such as "RIFF", without the string's
// hidden trailing '\0'.
void write_tag(std::FILE* f, const char* tag) {
    std::fwrite(tag, 1, 4, f);
}

}  // namespace

// -----------------------------------------------------------------------------
// Exercise 3, part A: open, write, finish
// -----------------------------------------------------------------------------

WavWriter::WavWriter(const std::filesystem::path& path, int sample_rate, int channels)
    : file_(std::fopen(path.c_str(), "wb")) {
    if (!file_) {
        throw std::runtime_error("could not open " + path.string());
    }

    const auto rate = static_cast<std::uint32_t>(sample_rate);
    const auto chans = static_cast<std::uint16_t>(channels);
    const auto block_align = static_cast<std::uint16_t>(chans * 2);  // bytes per frame
    std::FILE* f = file_.get();  // the raw FILE* for the C calls; file_ still owns it

    write_tag(f, "RIFF");
    write_le<std::uint32_t>(f, 0);  // 36 + data size, filled in by ~WavWriter
    write_tag(f, "WAVE");

    write_tag(f, "fmt ");
    write_le<std::uint32_t>(f, 16);  // size of the rest of this chunk
    write_le<std::uint16_t>(f, 1);   // integer PCM
    write_le(f, chans);
    write_le(f, rate);
    write_le<std::uint32_t>(f, rate * block_align);  // byte rate
    write_le(f, block_align);
    write_le<std::uint16_t>(f, 16);  // bits per sample

    write_tag(f, "data");
    write_le<std::uint32_t>(f, 0);  // data size, filled in by ~WavWriter
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
