#include <stdio.h>
#include <stdint.h>

#ifdef RV32ASM
struct timespec {
    __time_t tv_sec;
    long tv_nsec;
};
#else   // no RV32ASM
#include <time.h>
#endif  // RV32ASM

static inline struct timespec get_timespec() {
    struct timespec ts;
#ifdef RV32ASM
    asm volatile (
        "li a7, 403\n"
        "li a0, 1\n"
        "mv a1, %0\n"
        "ecall\n"
        :
        : "r"(&ts)
        : "a0", "a1", "a7"
    );
#else   // no RV32ASM
    clock_gettime(CLOCK_MONOTONIC, &ts);
#endif  // RV32ASM
    return ts;
}

static struct timespec start_ts, end_ts;

__attribute__((constructor)) void start_timer() {
    start_ts = get_timespec();
}

__attribute__((destructor)) void end_timer() {
    end_ts = get_timespec();
    
    long diff_sec, diff_nsec;
    if ((end_ts.tv_nsec - start_ts.tv_nsec) < 0) {
        diff_sec = end_ts.tv_sec - start_ts.tv_sec - 1;
        diff_nsec = end_ts.tv_nsec - start_ts.tv_nsec + 1000000000;
    } else {
        diff_sec = end_ts.tv_sec - start_ts.tv_sec;
        diff_nsec = end_ts.tv_nsec - start_ts.tv_nsec;
    }
    printf("Execution time: %ld s %ld ns\n", diff_sec, diff_nsec);
}