#ifndef INOUTSTREAMS_DEF
#define INOUTSTREAMS_DEF

#include "IncludeDefine.h"
#include SAMTOOLS_BGZF_H

#ifdef STAR_GZ_INPUT
  // STAR-crossplatform: native plain/gz/bz2 read input via GzIfstream
  #include "GzIfstream.h"
  typedef GzIfstream ReadInFstream;   // transparent plain/gz, streaming, all platforms
#else
  typedef std::ifstream ReadInFstream;
#endif

class InOutStreams {
    public:
    ostream *logStdOut, *outSAM;
    ofstream logStdOutFile, outSAMfile;
    BGZF *outBAMfileUnsorted, *outBAMfileCoord, *outQuantBAMfile;

    ofstream outChimSAM, outChimJunction, logMain, logProgress, logFinal, outUnmappedReadsStream[MAX_N_MATES];
    ReadInFstream readIn[MAX_N_MATES]; // STAR-crossplatform: GzIfstream-capable read stream type

    //compilation-optional streams
    ofstream outLocalChains;

    InOutStreams();
    ~InOutStreams();
};

#endif
