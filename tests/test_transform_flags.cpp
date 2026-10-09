// Regression for uninitialized/stale transformed-quantification selection.
// Link with ParametersGenome.cpp; no genome or htslib library is needed.
#include "ParametersGenome.h"
#include "ErrorWarning.h"
#include <stdexcept>

void exitWithError(string message, ostream &, ostream &, int, Parameters &) {
    throw std::runtime_error(message);
}

int main() {
    ParametersGenome genome;
    genome.gDir = "index";
    genome.gLoad = "NoSharedMemory";
    genome.gTypeString = "Full";
    genome.transform.typeString = "None";

    // Seed valid, non-default flags so the failure does not depend on stack
    // contents or platform. Also exercise reinitialization after Quant.
    for (unsigned mask = 0; mask < 8; ++mask) {
        genome.transform.output.clear();
        if (mask & 1) genome.transform.output.push_back("SAM");
        if (mask & 2) genome.transform.output.push_back("SJ");
        if (mask & 4) genome.transform.output.push_back("Quant");
        if (mask == 0) genome.transform.output.push_back("None");
        for (bool prior : {false, true}) {
            genome.transform.outYes = genome.transform.outSAM =
                genome.transform.outSJ = genome.transform.outQuant = prior;
            genome.initialize(nullptr); // valid parameters never use Parameters
            if (genome.transform.outYes != (mask != 0) ||
                genome.transform.outSAM != bool(mask & 1) ||
                genome.transform.outSJ != bool(mask & 2) ||
                genome.transform.outQuant != bool(mask & 4)) {
                cerr << "FAIL: transform flags for mask=" << mask
                     << " prior=" << prior << endl;
                return 1;
            }
        }
    }
    cout << "PASS: 16 transform flag initialization cases" << endl;
}
