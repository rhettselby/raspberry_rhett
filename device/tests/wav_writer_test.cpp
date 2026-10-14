// Tests for wav_writer.hpp. Each test writes a real file to the system temp
// directory, reads the bytes back and checks them against the header layout in
// wav_writer.cpp.
//
// Run one group:  ctest --test-dir device/build -R WavWriter --output-on-failure

#include "wav_writer.hpp"

#include <gtest/gtest.h>

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <system_error>
#include <utility>
#include <vector>

namespace device {
namespace {

// A file path in the temp directory. The file is deleted when the TempFile goes
// out of scope, even if the test fails: RAII again.
class TempFile {
public:
    explicit TempFile(const std::string& name)
        : path_(std::filesystem::temp_directory_path() / ("device_test_" + name + ".wav")) {}

    ~TempFile() {
        std::error_code ignored;  // destructors mustn't throw, so use the non-throwing overload
        std::filesystem::remove(path_, ignored);
    }

    TempFile(const TempFile&) = delete;
    TempFile& operator=(const TempFile&) = delete;

    const std::filesystem::path& path() const { return path_; }

private:
    std::filesystem::path path_;
};

std::vector<std::uint8_t> read_bytes(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}

// .at() throws if the file is too short, which fails the test cleanly instead
// of reading past the end of the vector.
std::uint16_t u16_at(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
    return static_cast<std::uint16_t>(bytes.at(offset) | bytes.at(offset + 1) << 8);
}

std::uint32_t u32_at(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
    return static_cast<std::uint32_t>(u16_at(bytes, offset)) |
           static_cast<std::uint32_t>(u16_at(bytes, offset + 2)) << 16;
}

std::int16_t i16_at(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
    return static_cast<std::int16_t>(u16_at(bytes, offset));
}

std::string tag_at(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
    std::string tag;
    for (std::size_t i = 0; i < 4; ++i) {
        tag += static_cast<char>(bytes.at(offset + i));
    }
    return tag;
}

// -----------------------------------------------------------------------------
// Exercise 3, part A: open, write, finish
// -----------------------------------------------------------------------------

TEST(WavWriter, ThrowsIfTheFileCannotBeOpened) {
    EXPECT_THROW(WavWriter("/no/such/directory/out.wav", 48000, 1), std::runtime_error);
}

TEST(WavWriter, WritesAValidHeader) {
    TempFile file("header");
    {
        WavWriter writer(file.path(), 48000, 1);
        writer.write(std::vector<float>(100, 0.0f));
    }  // the destructor finishes the file here

    const auto bytes = read_bytes(file.path());
    ASSERT_EQ(bytes.size(), 44u + 200) << "expected a 44-byte header and 100 samples of 2 bytes";
    EXPECT_EQ(tag_at(bytes, 0), "RIFF");
    EXPECT_EQ(u32_at(bytes, 4), 36u + 200);
    EXPECT_EQ(tag_at(bytes, 8), "WAVE");
    EXPECT_EQ(tag_at(bytes, 12), "fmt ");
    EXPECT_EQ(u32_at(bytes, 16), 16u);
    EXPECT_EQ(u16_at(bytes, 20), 1) << "format should be 1 (PCM)";
    EXPECT_EQ(u16_at(bytes, 22), 1) << "channels";
    EXPECT_EQ(u32_at(bytes, 24), 48000u) << "sample rate";
    EXPECT_EQ(u32_at(bytes, 28), 48000u * 2) << "byte rate";
    EXPECT_EQ(u16_at(bytes, 32), 2) << "block align";
    EXPECT_EQ(u16_at(bytes, 34), 16) << "bits per sample";
    EXPECT_EQ(tag_at(bytes, 36), "data");
    EXPECT_EQ(u32_at(bytes, 40), 200u) << "data size";
}

TEST(WavWriter, WritesStereoFormat) {
    TempFile file("stereo");
    {
        WavWriter writer(file.path(), 44100, 2);
        writer.write(std::vector<float>(10, 0.0f));  // 5 frames of left + right
    }

    const auto bytes = read_bytes(file.path());
    ASSERT_EQ(bytes.size(), 44u + 20);
    EXPECT_EQ(u16_at(bytes, 22), 2) << "channels";
    EXPECT_EQ(u32_at(bytes, 24), 44100u) << "sample rate";
    EXPECT_EQ(u32_at(bytes, 28), 44100u * 4) << "byte rate";
    EXPECT_EQ(u16_at(bytes, 32), 4) << "block align";
}

TEST(WavWriter, ConvertsAndClampsSamples) {
    TempFile file("convert");
    {
        WavWriter writer(file.path(), 48000, 1);
        writer.write(std::vector<float>{0.0f, 1.0f, -1.0f, 0.5f, 2.0f, -2.0f});
    }

    const auto bytes = read_bytes(file.path());
    ASSERT_EQ(bytes.size(), 44u + 12);
    EXPECT_EQ(i16_at(bytes, 44), 0);
    EXPECT_EQ(i16_at(bytes, 46), 32767);
    EXPECT_EQ(i16_at(bytes, 48), -32767);
    EXPECT_NEAR(i16_at(bytes, 50), 16384, 1);  // 0.5 * 32767 = 16383.5
    EXPECT_EQ(i16_at(bytes, 52), 32767) << "2.0 should be clamped to 1.0";
    EXPECT_EQ(i16_at(bytes, 54), -32767) << "-2.0 should be clamped to -1.0";
}

TEST(WavWriter, CountsSamplesAcrossWrites) {
    TempFile file("many_writes");
    {
        WavWriter writer(file.path(), 48000, 1);
        for (int i = 0; i < 3; ++i) {
            writer.write(std::vector<float>(10, 0.25f));
        }
    }

    const auto bytes = read_bytes(file.path());
    ASSERT_EQ(bytes.size(), 44u + 60);
    EXPECT_EQ(u32_at(bytes, 4), 36u + 60);
    EXPECT_EQ(u32_at(bytes, 40), 60u);
}

// -----------------------------------------------------------------------------
// Exercise 3, part B: moving. Until you've done part B these may crash rather
// than fail; ctest runs each test separately, so the others still report.
// -----------------------------------------------------------------------------

TEST(WavWriterMove, MoveConstructionHandsOverTheFile) {
    TempFile file("move_construct");
    {
        WavWriter first(file.path(), 48000, 1);
        first.write(std::vector<float>(10, 0.0f));
        WavWriter second(std::move(first));  // `first` now owns nothing
        second.write(std::vector<float>(5, 0.0f));
    }  // ~second finishes the file; ~first must do nothing

    const auto bytes = read_bytes(file.path());
    ASSERT_EQ(bytes.size(), 44u + 30);
    EXPECT_EQ(u32_at(bytes, 40), 30u);
}

TEST(WavWriterMove, MoveAssignmentFinishesTheOldFile) {
    TempFile old_file("move_assign_old");
    TempFile new_file("move_assign_new");
    {
        WavWriter writer(old_file.path(), 48000, 1);
        writer.write(std::vector<float>(10, 0.0f));
        WavWriter other(new_file.path(), 48000, 1);
        other.write(std::vector<float>(5, 0.0f));

        // `writer` lets go of old_file, which must be finished properly, and
        // takes over new_file from `other`.
        writer = std::move(other);
        writer.write(std::vector<float>(3, 0.0f));
    }

    const auto old_bytes = read_bytes(old_file.path());
    ASSERT_EQ(old_bytes.size(), 44u + 20);
    EXPECT_EQ(u32_at(old_bytes, 40), 20u) << "the old file was closed without finishing its header";

    const auto new_bytes = read_bytes(new_file.path());
    ASSERT_EQ(new_bytes.size(), 44u + 16);
    EXPECT_EQ(u32_at(new_bytes, 40), 16u);
}

}  // namespace
}  // namespace device
