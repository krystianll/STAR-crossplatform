// Small real-operation regressions for LLP64 counters and large-file I/O.
#include "Quantifications.h"
#include "sysRemoveDir.h"
#include <cstdio>
#if !defined(_WIN32)
#include <sys/statvfs.h>
#endif

int main(int argc, char **argv) {
    int failures = 0;
    auto check = [&](bool passed, const char *name) {
        cout << (passed ? "PASS: " : "FAIL: ") << name << endl;
        if (!passed) ++failures;
    };
    Quantifications a(1), b(1);
    a.geneCounts.cMulti = 0xffffffffULL;
    b.geneCounts.cMulti = 2;
    for (int i=0; i<3; ++i) {
        a.geneCounts.cAmbig[i] = a.geneCounts.cNone[i] = a.geneCounts.gCount[i][0] = 0xffffffffULL;
        b.geneCounts.cAmbig[i] = b.geneCounts.cNone[i] = b.geneCounts.gCount[i][0] = 2;
    }
    a.addQuants(b);
    bool counts = a.geneCounts.cMulti == 0x100000001ULL;
    for (int i=0; i<3; ++i)
        counts = counts && a.geneCounts.cAmbig[i] == 0x100000001ULL
            && a.geneCounts.cNone[i] == 0x100000001ULL
            && a.geneCounts.gCount[i][0] == 0x100000001ULL;
    check(counts, "gene-count accumulation across 2^32");
    if (argc != 3) {
        cerr << "Usage: test_platform_io <sparse-file> <disposable-directory-containing-it>\n";
        return 2;
    }
    const int64 expected = (1LL << 31) + 18;
    struct stat info;
    check(stat(argv[1], &info) == 0 && info.st_size == expected, "stat file larger than 2 GiB");
    ifstream file(argv[1], ios::binary | ios::ate);
    check(file && file.tellg() == expected, "tellg beyond 2 GiB");
    file.seekg(expected-1, ios::beg);
    check(file.get() == 'X', "seekg beyond 2 GiB");
    file.close();
    struct statvfs volume, parent;
    check(statvfs(argv[1], &volume) == 0 && statvfs(argv[2], &parent) == 0
          && volume.f_blocks*volume.f_frsize == parent.f_blocks*parent.f_frsize
          && volume.f_blocks > 0, "free-space query accepts a file on the target volume");
    check(statvfs((string(argv[2])+"/missing").c_str(), &volume) != 0,
          "free-space query does not silently use cwd for a missing path");
    sysRemoveDir(argv[2]);
    check(stat(argv[2], &info) != 0 && errno == ENOENT, "remove directory containing >2 GiB file");
    return failures ? 1 : 0;
}
