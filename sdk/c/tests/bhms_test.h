/* Minimal assert harness for the native tests (no external dependency). */
#ifndef BHMS_TEST_H
#define BHMS_TEST_H
#include <stdio.h>
#include <string.h>

static int bhms_t_fail, bhms_t_checks;

#define CHECK(cond)                                                              \
    do {                                                                         \
        ++bhms_t_checks;                                                         \
        if (!(cond)) {                                                           \
            ++bhms_t_fail;                                                       \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
        }                                                                        \
    } while (0)

#define CHECK_BYTES(actual, expected, n)                                         \
    do {                                                                         \
        ++bhms_t_checks;                                                         \
        if (memcmp((actual), (expected), (n)) != 0) {                            \
            ++bhms_t_fail;                                                       \
            fprintf(stderr, "FAIL %s:%d: bytes differ (%s)\n", __FILE__,         \
                    __LINE__, #actual);                                          \
            for (size_t k_ = 0; k_ < (size_t)(n); ++k_)                          \
                fprintf(stderr, "%02x", ((const unsigned char *)(actual))[k_]);  \
            fprintf(stderr, "\n");                                               \
            for (size_t k_ = 0; k_ < (size_t)(n); ++k_)                          \
                fprintf(stderr, "%02x", ((const unsigned char *)(expected))[k_]);\
            fprintf(stderr, "\n");                                               \
        }                                                                        \
    } while (0)

#define TEST_FINISH(name)                                                        \
    do {                                                                         \
        printf("%s: %d checks, %d failures\n", name, bhms_t_checks, bhms_t_fail);\
        return bhms_t_fail ? 1 : 0;                                              \
    } while (0)

#endif
