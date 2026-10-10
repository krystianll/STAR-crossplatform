#if defined(_WIN32)
// STAR-crossplatform: Select MinGW's nftw64 callback ABI as well as its 64-bit stat structure.
#undef _FILE_OFFSET_BITS
#define _FILE_OFFSET_BITS 64
#endif
#include <string>
#include <cstring>
//#define _XOPEN_SOURCE 500
#include <ftw.h>
#include <unistd.h>

int removeFileOrDir(const char *fpath,const struct stat *sb, int typeflag, struct FTW *ftwbuf) {

    {//to avoid unused variable warning
        (void) sb;
        (void) ftwbuf;
    };

    if (typeflag==FTW_F) {//file
        remove(fpath);
    } else if (typeflag==FTW_DP) {//dir
        rmdir(fpath);
    } else {//something went wrong, stop the removal
        return -1;
    };
    return 0;
};


void sysRemoveDir(std::string dirName) {//remove directory and all its contents
    int nftwFlag=FTW_DEPTH;
    nftw(dirName.c_str(), removeFileOrDir, 100, nftwFlag);
};
