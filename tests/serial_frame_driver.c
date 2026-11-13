/* Native test harness only: stdio is not part of the endpoint parser. */
#include <stdio.h>
#include <string.h>
#include "../protocol/serial/frame.h"

int main(int argc, char **argv) {
    hms_frame_parser parser;
    int ch;
    if (argc == 2 && strcmp(argv[1], "--size") == 0) {
        printf("%zu\n", sizeof(parser));
        return 0;
    }
    hms_frame_reset(&parser);
    while ((ch = getchar()) != EOF) {
        hms_frame_result result = hms_frame_feed(&parser, (uint8_t)ch);
        if (result == HMS_FRAME_READY) {
            unsigned i;
            unsigned count = HMS_FRAME_HEADER + ((unsigned)parser.raw[18] << 8) + parser.raw[19] + 2u;
            printf("F ");
            for (i = 0; i < count; ++i) printf("%02x", parser.raw[i]);
            putchar('\n');
        } else if (result != HMS_FRAME_NONE) {
            puts("E");
        }
    }
    return ferror(stdin) ? 1 : 0;
}
