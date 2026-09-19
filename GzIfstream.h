#ifndef STAR_GZIFSTREAM_H
#define STAR_GZIFSTREAM_H

// A drop-in std::istream for read files that transparently decompresses gzip
// input and passes uncompressed input through, via zlib's gzFile. Sequential
// only (STAR reads read-files sequentially; it never seeks them). Lets the
// default input path handle plain OR .gz FASTQ on every platform, streaming,
// with no temp file and no external process. See WINDOWS_BUILD.md §12.
//
// Also concatenates a *list* of files (STAR's comma-separated --readFilesIn),
// decompressing each in turn. This is done here (not via an external "cat" into
// a fifo) because zlib only auto-detects gzip from the first bytes of a stream:
// piping "FILE 0\n<gz1>FILE 1\n<gz2>" through one gzopen would start in
// passthrough mode and never inflate. Opening each file with its own gzopen
// inflates every member and works on all platforms (no fork/fifo needed).
// We do, however, re-synthesize upstream's "FILE <n>" boundary marker ahead of
// each file (see openNext/underflow), so the chunk reader still advances
// readFilesIndex and per-file read groups / STARsolo barcode indexing keep working.

#include <istream>
#include <streambuf>
#include <ios>
#include <string>
#include <vector>
#include <zlib.h>

class GzStreambuf : public std::streambuf {
    gzFile gz_;
    std::vector<std::string> paths_;    // remaining files to concatenate
    size_t idx_;                        // next file to open in paths_
    std::string pending_;               // synthesized "FILE n" marker to emit before next file
    static const int BUFSZ = 1 << 16;   // 64 KiB read chunk
    char buf_[BUFSZ];

    // Open the next file in paths_ into gz_. Returns false when the list is
    // exhausted or a file cannot be opened (caller pre-validates paths).
    bool openNext() {
        while (idx_ < paths_.size()) {
            size_t fileIdx = idx_;       // 0-based index of the file being opened
            gz_ = gzopen(paths_[idx_++].c_str(), "rb");
            if (!gz_) return false;      // rare: openReadsFiles stat()s first
            gzbuffer(gz_, 1 << 20);      // larger internal zlib buffer (perf)
            // Emit STAR's "FILE <n>" boundary marker ahead of this file's bytes,
            // so the chunk reader (ReadAlignChunk_processChunks) advances
            // readFilesIndex -> per-file --outSAMattrRGline read groups and
            // STARsolo per-file barcode indexing work. Upstream inserts these via
            // its cat/fifo concatenation; we synthesize them because GzIfstream
            // concatenates the comma-separated list itself.
            pending_ = "FILE " + std::to_string(fileIdx) + "\n";
            setg(buf_, buf_, buf_);      // empty get area -> underflow on read
            return true;
        }
        return false;
    }
public:
    GzStreambuf() : gz_(0), idx_(0) {}
    ~GzStreambuf() { close(); }
    GzStreambuf(const GzStreambuf&) = delete;
    GzStreambuf& operator=(const GzStreambuf&) = delete;

    bool is_open() const { return gz_ != 0; }

    // Open a single file (plain or .gz).
    bool open(const char* path) {
        std::vector<std::string> one(1, std::string(path));
        return openList(one);
    }

    // Open a list of files, concatenated and each decompressed as needed.
    bool openList(const std::vector<std::string>& paths) {
        close();
        paths_ = paths;
        idx_ = 0;
        return openNext();
    }

    void close() {
        if (gz_) { gzclose(gz_); gz_ = 0; }
        paths_.clear();
        idx_ = 0;
        pending_.clear();
        setg(0, 0, 0);
    }

protected:
    // Serve the synthesized "FILE n" marker (if any) into the get area, else read
    // the next block of file bytes. Returns the first char, or eof().
    int_type servePendingOrEof() {
        size_t k = pending_.copy(buf_, BUFSZ);   // "FILE n\n" always fits in BUFSZ
        pending_.clear();
        setg(buf_, buf_, buf_ + k);
        return traits_type::to_int_type(*gptr());
    }
    int_type underflow() {
        if (!gz_) return traits_type::eof();
        if (gptr() < egptr())
            return traits_type::to_int_type(*gptr());
        if (!pending_.empty())                    // marker before the current file's bytes
            return servePendingOrEof();
        int n;
        for (;;) {
            n = gzread(gz_, buf_, BUFSZ);
            if (n > 0) break;                 // got data
            // n==0 (EOF) or n<0 (error): current file done -> next file, if any
            gzclose(gz_); gz_ = 0;
            if (!openNext()) return traits_type::eof();
            if (!pending_.empty())                // marker before the next file's bytes
                return servePendingOrEof();
        }
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

    // Open a list of files (STAR's comma-separated --readFilesIn), concatenated
    // and each decompressed transparently.
    void openMulti(const std::vector<std::string>& paths) {
        if (sb_.openList(paths)) { clear(); }
        else { setstate(std::ios_base::failbit); }
    }

    bool is_open() const { return sb_.is_open(); }
    void close() { sb_.close(); }
};

#endif
