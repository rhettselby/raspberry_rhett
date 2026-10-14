# device (C++)

The time-critical half of the project: audio, noise generation, Bluetooth, alarms and buttons. It has to keep working even when the Python assistant crashes.

It currently holds **milestone 1, the noise generator**, set up as exercises. The build, the tests and the tools are written. The parts marked `TODO(you)` are yours to implement, and the tests say when each one is done. Nothing in this milestone needs the Pi.

## Setup on the Mac

Install CMake:

```bash
brew install cmake
```

For the spectrum plots in exercise 6, make a Python virtual environment at the repo root (`.venv/` is already gitignored):

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install numpy matplotlib
```

On the Pi later, `sudo apt install cmake g++` is all you need.

## Build and test

Run these from the repo root. **Configure** once. It generates Makefiles in `device/build` and downloads GoogleTest the first time:

```bash
cmake -S device -B device/build
```

**Build** after every change:

```bash
cmake --build device/build
```

**Test**:

```bash
ctest --test-dir device/build --output-on-failure
```

Run one group of tests with `-R` (a regex on the test names):

```bash
ctest --test-dir device/build -R WhiteNoise --output-on-failure
```

At first all 26 tests fail. That's expected: each exercise turns one group green.

The build includes AddressSanitizer and UndefinedBehaviorSanitizer. If a test or program stops with a report like `ERROR: AddressSanitizer: heap-buffer-overflow`, look down the stack trace for the first line in your own file (`noise.cpp:42`). That's where the bug is. Treat a sanitizer report as a real bug, even when the test it came from passed.

If you use VS Code with the clangd extension, it picks up `device/build/compile_commands.json` automatically for autocompletion and inline errors.

## Files

| File | What it is | Who writes it |
|---|---|---|
| `CMakeLists.txt` | The build: a library, a tool and the tests | Given. Read the comments |
| `src/noise.hpp` | The noise generator classes | Given. You add the private members |
| `src/noise.cpp` | The noise generators | **You** |
| `src/wav_writer.hpp` | The WAV file writer class | Given. You add the private members |
| `src/wav_writer.cpp` | The WAV file writer | **You** |
| `tests/` | GoogleTest tests that define "done" | Given. Don't edit them to make them pass |
| `tools/noise_gen.cpp` | Command line: noise to a WAV file | Given |
| `tools/plot_spectrum.py` | Measures and plots the spectrum | Given |

## How to work through the exercises

- Do one exercise at a time. Build often: after every few lines, not after the whole file.
- When the compiler prints a wall of errors, read only the **first** one. The rest are often knock-on effects.
- Look things up on [cppreference.com](https://en.cppreference.com). Learning to read it is part of the skill. The links below go straight to the relevant pages.
- `-Wconversion` is on, so the compiler warns about silent conversions (double to float, int to `int16_t`). Fix every warning, usually with a `float` literal (`0.5f`) or a `static_cast`.
- When you use a parameter that has `[[maybe_unused]]` in front of it, delete the attribute.
- Stuck? Ask Claude for a hint, and say how big: "a nudge", "which function should I use", or "show me the line".
- Commit after each exercise.

---

### Exercise 0: Read the build

Read `CMakeLists.txt`, then configure, build and run the tests. Everything fails. Before moving on, make sure you can answer these:

- What's the difference between configuring and building? When would you need to configure again? (Hint: when you add a new `.cpp` file.)
- What are the three *targets*, and which depends on which?
- Why is the code in a library (`device_core`) instead of being compiled into each program?
- What does `PUBLIC` mean in `target_include_directories`, and why is it `PRIVATE` for the warnings?

### Exercise 1: White noise

**Files:** `noise.hpp` (`WhiteNoise`'s `private:` section), `noise.cpp` · **Tests:** `WhiteNoise`

White noise is just a stream of independent random numbers. This exercise is about the basic parts of a class.

**Concepts**

- [Classes](https://en.cppreference.com/w/cpp/language/classes), and the [member initializer list](https://en.cppreference.com/w/cpp/language/constructor) (`WhiteNoise(std::uint32_t seed) : engine_(seed) {}`). Members are initialized there, *before* the constructor body runs.
- [`<random>`](https://en.cppreference.com/w/cpp/numeric/random) separates two jobs. An **engine** such as [`std::mt19937`](https://en.cppreference.com/w/cpp/numeric/random/mersenne_twister_engine) produces raw random bits. A **distribution** such as [`std::uniform_real_distribution<float>`](https://en.cppreference.com/w/cpp/numeric/random/uniform_real_distribution) turns them into numbers in the range you want. Both keep state between calls, so both are members.
- [`std::span`](https://en.cppreference.com/w/cpp/container/span): a view of contiguous memory that you don't own, made of a pointer and a length. A `std::vector<float>` converts to one automatically, and a range-based `for` loop works on it.
- [`virtual` and `override`](https://en.cppreference.com/w/cpp/language/override): `fill()` calls `next()`, and C++ picks the right `next()` for the actual object at runtime.

**Steps**

1. Implement `NoiseSource::fill`: set every element of `out` to `next()`. A range-based `for` loop is enough. Think about why the loop variable has to be a reference (`float&`).
2. Add two members to `WhiteNoise`: an engine and a distribution. The usual style is a trailing underscore (`engine_`), so members are easy to tell apart from parameters.
3. Seed the engine in the constructor's member initializer list.
4. `next()` returns the distribution called with the engine.

**Pitfalls**

- Don't create the engine inside `next()`. It would be re-seeded on every call and return the same number every time.
- `std::uniform_real_distribution<float>{-1.0f, 1.0f}` covers [-1, 1), which is fine.

### Exercise 2: `make_noise`

**Files:** `noise.cpp` · **Tests:** `MakeNoise`

`noise_gen` doesn't know which color it wants until runtime. `make_noise` hides that choice behind a pointer to the base class.

**Concepts**

- [`std::unique_ptr`](https://en.cppreference.com/w/cpp/memory/unique_ptr): exactly one owner, which deletes the object automatically when it goes away. Create one with [`std::make_unique<T>(args...)`](https://en.cppreference.com/w/cpp/memory/unique_ptr/make_unique), and never write `new` or `delete` yourself.
- A `std::unique_ptr<WhiteNoise>` converts to a `std::unique_ptr<NoiseSource>`. This is where the base class's `virtual` destructor matters: without it, deleting through the base pointer would skip `~WhiteNoise()`.
- A [`switch`](https://en.cppreference.com/w/cpp/language/switch) on an `enum class`, with one `case` per color.

**Steps:** write a `switch` on `color` in which each `case` returns `std::make_unique<...>(seed)`. `PinkNoise` and `BrownNoise` are still stubs, but they exist, so you can create them already.

**Pitfall:** clang on the Mac accepts a `switch` that returns in every case, but GCC on the Pi warns "control reaches end of non-void function". GCC has a point: an `enum class` variable can hold values that aren't listed. Add a line after the `switch` that [throws](https://en.cppreference.com/w/cpp/language/throw) `std::invalid_argument`.

### Exercise 3: WAV writer (RAII around a C API)

**Files:** `wav_writer.hpp` (`private:` section), `wav_writer.cpp` · **Tests:** `WavWriter` (part A), `WavWriterMove` (part B)

This is the most important exercise in milestone 1. The same pattern will wrap ALSA (`snd_pcm_open` / `snd_pcm_close`) in milestone 2, and BlueZ after that.

#### Part A: open, write, finish

**Concepts**

- [**RAII**](https://en.cppreference.com/w/cpp/language/raii): the constructor acquires a resource, and the destructor releases it. The resource then lives exactly as long as the object, so you can't forget to close it, and an exception can't leak it.
- The C file API: [`std::fopen`](https://en.cppreference.com/w/cpp/io/c/fopen) (`"wb"`, write binary), [`std::fwrite`](https://en.cppreference.com/w/cpp/io/c/fwrite), [`std::fseek`](https://en.cppreference.com/w/cpp/io/c/fseek) and `std::fclose`. `path.c_str()` gives the `const char*` that `fopen` wants.
- A **`std::unique_ptr` with a custom deleter**: `std::unique_ptr<std::FILE, FileCloser>`, where `FileCloser` is a small struct whose `operator()(std::FILE*)` calls `std::fclose`. The `unique_ptr` closes the file for you, including when the constructor throws partway through.
- **Throwing from a constructor**: if the constructor throws, the object never existed and its destructor doesn't run. Members that were already built are still destroyed, which is another reason to keep the file in a `unique_ptr` member.
- Binary output: fixed-width integers (`std::uint16_t`, `std::uint32_t`, `std::int16_t`) written little-endian. Both the Mac and the Pi are little-endian, so writing an integer's bytes as they sit in memory is correct. Document that assumption with `static_assert(std::endian::native == std::endian::little);` from [`<bit>`](https://en.cppreference.com/w/cpp/types/endian).
- A small [function template](https://en.cppreference.com/w/cpp/language/function_template) saves a lot of repetition: `template <typename T> void write_le(std::FILE* f, T value)`. Put helpers like this in an anonymous namespace at the top of the `.cpp`.
- Converting samples: [`std::clamp`](https://en.cppreference.com/w/cpp/algorithm/clamp), multiply by `32767.0f`, [`std::lround`](https://en.cppreference.com/w/cpp/numeric/math/round), then `static_cast<std::int16_t>`.

**Steps**

1. Members: the file, plus whatever you need to fill in the two sizes at the end. What do you need to count?
2. Constructor: open the file. If that fails, throw `std::runtime_error` with the path in the message. Then write the 44-byte header (the layout is in the comment at the top of `wav_writer.cpp`), with 0 for both sizes.
3. `write()`: convert and write each sample, and update your count.
4. Destructor: if you still own a file, seek to offset 4 and write `36 + data size`, then seek to 40 and write the data size. The `unique_ptr` closes the file afterwards.

A destructor must never throw. If `fseek` fails there, there's nothing sensible to do, so ignore it.

**Then listen to it.** Exercises 1 to 3 are all `noise_gen` needs. Turn the volume down first:

```bash
./device/build/noise_gen white 5 white.wav
```

```bash
afplay white.wav
```

#### Part B: moving

`WavWriter` can't be copied: two objects can't both own one file. Ownership can be *moved*, though, which is how a function can return a `WavWriter` or a `std::vector` can hold them.

**Concepts**

- [Move constructors](https://en.cppreference.com/w/cpp/language/move_constructor) and [move assignment](https://en.cppreference.com/w/cpp/language/move_assignment). `WavWriter&&` binds to an object that's about to be thrown away.
- [`std::move`](https://en.cppreference.com/w/cpp/utility/move) doesn't move anything. It's a cast that says "you may steal from this".
- The **moved-from state**: after a move, `other` must still be safe to destroy. Here, that means it owns no file, and its destructor does nothing.
- [`std::exchange`](https://en.cppreference.com/w/cpp/utility/exchange) gives you the old value and resets it in a single step.
- The [rule of three/five/zero](https://en.cppreference.com/w/cpp/language/rule_of_three). Moves are marked `noexcept` because containers like `std::vector` rely on that to move elements safely when they grow.

**Steps**

1. Move constructor: take over `other`'s members, and leave `other` empty.
2. Move assignment: `*this` might already own a file. What has to happen to that file before you take over `other`'s? The test `MoveAssignmentFinishesTheOldFile` checks this. Hint: move the header-finishing code from the destructor into a private `finish()` function, and call it from both places.

To think about: if the `unique_ptr` were your only member, would `= default` be correct for the move constructor? For move assignment? Why not?

Until part B is done, the `WavWriterMove` tests may crash instead of failing, for example by writing through a null `FILE*`. `ctest` runs every test in its own process, so the other results still show up. To run only part A, use `-R 'WavWriter\.'`.

### Exercise 4: Brown noise

**Files:** `noise.hpp`, `noise.cpp` · **Tests:** `BrownNoise`

Brown noise is a running sum of white noise: each sample is the previous one plus a small random step. That makes it a deep rumble, with power falling 6 dB per octave.

**Concepts**

- **Composition**: a `BrownNoise` *has a* `WhiteNoise` member. `WhiteNoise` has no default constructor, so you must initialize it in the member initializer list. The compiler error you get if you don't is worth reading once.
- State that carries over between calls to `next()`.
- [`constexpr`](https://en.cppreference.com/w/cpp/language/constexpr) for named constants (`constexpr float kLeak = 0.98f;`) instead of bare numbers in the code.

**The catch:** a plain running sum is a random walk. It drifts away from 0 and gets stuck at the edges of [-1, 1], and the `DoesNotDrift` test catches that. The fix is a **leak**: shrink the running value slightly toward 0 on every step:

```
level = leak * level + (1 - leak) * white
```

A `leak` of 0.98 to 0.995 works well. The result is quiet, so multiply it up: with a leak of 0.98, a factor of about 3.5 gives an RMS level of about 0.2. Then `std::clamp` to [-1, 1].

The leak flattens the spectrum below about `(1 - leak) * 48000 / (2π)` Hz, which is about 150 Hz for 0.98. That's why the spectrum check in exercise 6 measures the slope from 500 Hz up.

### Exercise 5: Pink noise

**Files:** `noise.hpp`, `noise.cpp` · **Tests:** `PinkNoise`

Pink noise sits between white and brown. Power falls 3 dB per octave, so every octave carries equal energy, which sounds like steady rain. No single simple filter makes it, so this uses **Paul Kellet's method**: several leaky integrators like the one in brown noise, each with a different leak so it covers a different band, added together.

For each new white sample `w`, update six filters as `b[i] = leak[i] * b[i] + gain[i] * w`:

| i | leak | gain |
|---|---|---|
| 0 | 0.99886 | 0.0555179 |
| 1 | 0.99332 | 0.0750759 |
| 2 | 0.96900 | 0.1538520 |
| 3 | 0.86650 | 0.3104856 |
| 4 | 0.55000 | 0.5329522 |
| 5 | -0.7616 | -0.0168980 |

Then the output is `b[0] + ... + b[5] + b[6] + w * 0.5362`, where `b[6]` is the previous sample's `w * 0.115926`. Only after computing the output, set `b[6] = w * 0.115926` for next time. Scale the result by about 0.11 and clamp it.

**Concepts**

- [`std::array`](https://en.cppreference.com/w/cpp/container/array) for fixed-size state: `std::array<float, 7> b_{};` (the `{}` zero-initializes it).
- A table of constants as a `static constexpr std::array` of a small struct, so a loop can replace six copy-pasted lines. Try both versions and decide which reads better.

### Exercise 6: Check the spectrum

This is milestone 1's actual goal. Generate 30 seconds of each color:

```bash
./device/build/noise_gen white 30 white.wav
```

```bash
./device/build/noise_gen pink 30 pink.wav
```

```bash
./device/build/noise_gen brown 30 brown.wav
```

Then measure them:

```bash
.venv/bin/python device/tools/plot_spectrum.py white.wav pink.wav brown.wav --out docs/noise-spectrum.png
```

You should see slopes of about 0, -3 and -6 dB per octave, and a plot with your three curves along the dashed guide lines. `.wav` files are gitignored. The plot is worth committing as proof that milestone 1 works.

## After milestone 1

Milestone 2 needs the Pi. An `AlsaSink` class wraps `snd_pcm_t*` the way `WavWriter` wraps `FILE*`. An `AudioSink` interface lets the generator write to either one, so the Mac keeps writing WAV files while the Pi plays sound. A lock-free ring buffer passes audio from the generator thread to the audio thread. The ring buffer is pure C++, so it can be built and tested on the Mac too.
