#include "streamFuns.h"
#include "ErrorWarning.h"
#include <stdexcept>
#include <cstdio>
#include <cerrno>
// Only initialize the streams consumed by the real streamFuns.cpp operations.
Parameters::Parameters() { inOut = new InOutStreams; }
void exitWithError(string message, ostream &, ostream &, int code, Parameters &) {
    if (code != EXIT_CODE_FILE_WRITE) throw std::runtime_error(message);
    throw code;
}
int main(int argc,char **argv) {
    if(argc!=2) return 2;
    Parameters p;
    std::ofstream output(argv[1],std::ios::binary);
    output << "partial"; output.flush();
    if (!output) throw std::runtime_error("could not create the partial-output fixture");
    output.setstate(std::ios::badbit); // deterministic write failure, without filling a disk
    bool failed=false;
    try { char c='X'; fstreamWriteBig(output,&c,1,argv[1],"regression",p); }
    catch(int code) { failed=(code==EXIT_CODE_FILE_WRITE); }
    struct stat st;
    bool removed=stat(argv[1],&st)==-1 && errno==ENOENT;
    std::cout << (failed && removed ? "PASS: " : "FAIL: ") << "write error reported=" << failed << " partial file removed=" << removed << '\n';
    output.close(); delete p.inOut;
    return failed && removed ? 0 : 1;
}
