#include "ThreadControl.h"

ThreadControl::ThreadControl() {
    chunkInN=0;
    chunkOutN=0;
    // Upstream never initialized this one; it is locked even with one thread.
    pthread_mutex_init(&mutexLogMain, NULL);
//     chunkOutBAMposition=new uint [MAX_chunkOutBAMposition];
};