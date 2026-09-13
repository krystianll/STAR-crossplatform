#ifndef STAR_GZIFSTREAM_H
#define STAR_GZIFSTREAM_H

// A drop-in std::istream for read files that transparently decompresses gzip
// input and passes uncompressed input through, via zlib's gzFile. Sequential
// only (STAR reads read-files sequentially; it never seeks them). Lets the
// default input path handle plain OR .gz FASTQ on every platform, streaming,
// with no temp file and no external process. See WINDOWS_BUILD.md §12.

#include <istream>
#include <streambuf>
#include <ios>
#include <zlib.h>

class GzStreambuf : public std::streambuf {
    gzFile gz_;
    static const int BUFSZ = 1 << 16;   // 64 KiB read chunk
    char buf_[BUFSZ];
public:
    GzStreambuf() : gz_(0) {}
    ~GzStreambuf() { close(); }
    GzStreambuf(const GzStreambuf&) = delete;
    GzStreambuf& operator=(const GzStreambuf&) = delete;

    bool is_open() const { return gz_ != 0; }

    bool open(const char* path) {
        close();
        gz_ = gzopen(path, "rb");        // gzread() auto-detects: .gz -> inflate, else passthrough
        if (!gz_) return false;
        gzbuffer(gz_, 1 << 20);          // larger internal zlib buffer (perf; ignore failure)
        setg(buf_, buf_, buf_);          // empty get area -> underflow on first read
        return true;
    }

    void close() {
        if (gz_) { gzclose(gz_); gz_ = 0; }
        setg(0, 0, 0);
    }

protected:
    int_type underflow() {
        if (!gz_) return traits_type::eof();
        if (gptr() < egptr())
            return traits_type::to_int_type(*gptr());
        int n = gzread(gz_, buf_, BUFSZ);
        if (n <= 0) return traits_type::eof();   // 0 = EOF, <0 = error -> treated as EOF
        setg(buf_, buf_, buf_ + n);
        return traits_type::to_int_type(*gptr());
    }
};

// IS-A std::istream, so operator>>, getline, peek, ignore, good, gcount, fail,
// clear, eof all work unchanged; we add ifstream's open/close/is_open.
class GzIfstream : public std::istream {
    GzStreambuf sb_;
public:
    // Associate the (empty) streambuf at construction so an unopened stream is
    // good() == true, exactly like a default-constructed std::ifstream. STAR's
    // chunk loop gates on readIn[1].good() even for single-end input, so an
    // unopened mate must report good() (rdbuf() clears the state flags).
    GzIfstream() : std::istream(0) { rdbuf(&sb_); }
    explicit GzIfstream(const char* path) : std::istream(0) { rdbuf(&sb_); open(path); }

    void open(const char* path) {
        if (sb_.open(path)) { clear(); }
        else { setstate(std::ios_base::failbit); }
    }
    void open(const std::string& path) { open(path.c_str()); }
    bool is_open() const { return sb_.is_open(); }
    void close() { sb_.close(); }
};

#endif
