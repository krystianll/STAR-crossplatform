#ifndef STAR_GZIFSTREAM_H
#define STAR_GZIFSTREAM_H

// A drop-in std::istream for read files that transparently decompresses gzip
// or bzip2 input and passes uncompressed input through: zlib's gzFile reads
// gzip and plain files, libbz2 reads a regular file that starts with a bzip2
// header (recognised by its bytes, not its name). Sequential
// only (STAR reads read-files sequentially; it never seeks them). Lets the
// default input path handle plain, .gz OR .bz2 FASTQ on every platform, streaming,
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
#include <iostream>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <sys/stat.h>
#include <zlib.h>
#if defined(_WIN32) && defined(__GNUC__) && !defined(_WINDOWS_)
// bzlib.h includes <windows.h> on Windows but, with GCC/Clang, uses nothing
// from it; its macros collide with STAR's (see IncludeDefine.h), so skip it.
#define _WINDOWS_
#include <bzlib.h>
#undef _WINDOWS_
#else
#include <bzlib.h>
#endif

class GzStreambuf : public std::streambuf {
    gzFile gz_;                         // gzip or plain input
    FILE *bzFile_;                      // bzip2 input: the file bz_ reads from
    BZFILE *bz_;                        // 0 after the last stream (bzFile_ stays open)
    bool bzMore_;                       // bz_ is a follow-on stream with no data yet
    std::vector<std::string> paths_;    // remaining files to concatenate
    size_t idx_;                        // next file to open in paths_
    std::string pending_;               // synthesized "FILE n" marker to emit before next file
    static const int BUFSZ = 1 << 16;   // 64 KiB read chunk
    char buf_[BUFSZ];

    void readError(const char *message) const {
        std::cerr << "EXITING because of fatal input ERROR: " << paths_[idx_-1]
                  << ": " << message << '\n';
        std::exit(EXIT_FAILURE);
    }

    // True if the first bytes are a bzip2 header: "BZh", a block size '1'-'9',
    // then the 48-bit magic of the first block (or of the end of an empty
    // stream). FASTQ/FASTA/SAM files cannot start like this.
    static bool isBzip2(const unsigned char *b, size_t n) {
        static const unsigned char block[6] = {0x31, 0x41, 0x59, 0x26, 0x53, 0x59};
        static const unsigned char end[6] = {0x17, 0x72, 0x45, 0x38, 0x50, 0x90};
        return n >= 10 && b[0] == 'B' && b[1] == 'Z' && b[2] == 'h' && b[3] >= '1' && b[3] <= '9'
               && (std::memcmp(b + 4, block, 6) == 0 || std::memcmp(b + 4, end, 6) == 0);
    }

    static const char *bzMessage(int err) {
        return err == BZ_UNEXPECTED_EOF ? "truncated bzip2 input"
             : err == BZ_IO_ERROR ? "bzip2 read error"
             : err == BZ_MEM_ERROR ? "out of memory decompressing bzip2 input"
             : "invalid bzip2 data";
    }

    // Open path through libbz2 if it is a regular file with a bzip2 header.
    // Returns false, with nothing open, for any other input (zlib reads it).
    // Only regular files are sniffed, so no bytes are taken from a pipe.
    bool openBzip2(const char *path) {
        struct stat st;
        if (stat(path, &st) != 0 || !S_ISREG(st.st_mode)) return false;
        FILE *f = std::fopen(path, "rb");
        if (!f) return false;
        unsigned char head[10];
        size_t n = std::fread(head, 1, sizeof(head), f);
        if (!isBzip2(head, n)) { std::fclose(f); return false; }
        int err = BZ_OK;
        if (std::fseek(f, 0, SEEK_SET) == 0) bz_ = BZ2_bzReadOpen(&err, f, 0, 0, NULL, 0);
        if (!bz_ || err != BZ_OK) {
            if (bz_) BZ2_bzReadClose(&err, bz_);
            bz_ = 0;
            std::fclose(f);
            readError("could not open bzip2 input");
        }
        bzFile_ = f;
        bzMore_ = false;
        return true;
    }

    void closeFile() {
        if (gz_) { gzclose(gz_); gz_ = 0; }
        if (bz_) { int err; BZ2_bzReadClose(&err, bz_); bz_ = 0; }
        if (bzFile_) { std::fclose(bzFile_); bzFile_ = 0; }
    }

    // Read up to BUFSZ bytes of bzip2 data, continuing through concatenated
    // streams as `bzip2 -dc` does. Bytes after the last stream that do not
    // start another one are ignored, also as `bzip2 -dc` does; any other
    // error (bad data, a truncated stream) is fatal. Returns 0 at end of file.
    int bzRead() {
        int got = 0;
        while (got < BUFSZ && bz_) {
            int err = BZ_OK;
            int n = BZ2_bzRead(&err, bz_, buf_ + got, BUFSZ - got);
            if (err == BZ_OK) { got += n; bzMore_ = false; continue; }
            if (err == BZ_DATA_ERROR_MAGIC && bzMore_) {   // trailing garbage
                BZ2_bzReadClose(&err, bz_); bz_ = 0;
                break;
            }
            if (err != BZ_STREAM_END) readError(bzMessage(err));
            got += n;
            void *unused = 0;
            int nUnused = 0;
            char next[BZ_MAX_UNUSED];
            BZ2_bzReadGetUnused(&err, bz_, &unused, &nUnused);
            if (nUnused > 0) std::memcpy(next, unused, nUnused);
            BZ2_bzReadClose(&err, bz_); bz_ = 0;
            int c = nUnused > 0 ? EOF : std::getc(bzFile_);
            if (c != EOF) std::ungetc(c, bzFile_);
            if (nUnused > 0 || c != EOF) {                 // another stream follows
                bz_ = BZ2_bzReadOpen(&err, bzFile_, 0, 0, next, nUnused);
                if (err != BZ_OK) readError(bzMessage(err));
                bzMore_ = true;
            }
        }
        return got;
    }

    // Open the next file in paths_ (bzip2 into bz_, else into gz_). Returns
    // false when the list is exhausted or a file cannot be opened (caller
    // pre-validates paths).
    bool openNext() {
        while (idx_ < paths_.size()) {
            size_t fileIdx = idx_;       // 0-based index of the file being opened
            const char *path = paths_[idx_++].c_str();
            if (!openBzip2(path)) {
                gz_ = gzopen(path, "rb");
                if (!gz_) return false;  // rare: openReadsFiles stat()s first
                gzbuffer(gz_, 1 << 20);  // larger internal zlib buffer (perf)
            }
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
    GzStreambuf() : gz_(0), bzFile_(0), bz_(0), bzMore_(false), idx_(0) {}
    ~GzStreambuf() { close(); }
    GzStreambuf(const GzStreambuf&) = delete;
    GzStreambuf& operator=(const GzStreambuf&) = delete;

    bool is_open() const { return gz_ != 0 || bzFile_ != 0; }

    // Open a single file (plain, .gz or .bz2).
    bool open(const char* path) {
        std::vector<std::string> one(1, std::string(path));
        bool opened = openList(one);
        pending_.clear(); // direct single-file reads (e.g. SAM headers) need no marker
        return opened;
    }

    // Open a list of files, concatenated and each decompressed as needed.
    bool openList(const std::vector<std::string>& paths) {
        close();
        paths_ = paths;
        idx_ = 0;
        return openNext();
    }

    void close() {
        closeFile();
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
        if (!gz_ && !bzFile_) return traits_type::eof();
        if (gptr() < egptr())
            return traits_type::to_int_type(*gptr());
        if (!pending_.empty())                    // marker before the current file's bytes
            return servePendingOrEof();
        int n;
        for (;;) {
            if (bzFile_) {
                n = bzRead();
            } else {
                n = gzread(gz_, buf_, BUFSZ);
                int error = Z_OK;
                const char *message = gzerror(gz_, &error);
                if (n < 0 || (error != Z_OK && error != Z_STREAM_END))
                    readError(message); // corrupt/truncated gzip must not become successful EOF
            }
            if (n > 0) break;                 // got data, with no deferred read error
            closeFile();
            if (idx_ == paths_.size()) return traits_type::eof();
            if (!openNext()) readError("could not open input file");
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
