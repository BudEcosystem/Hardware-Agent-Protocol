/* In-memory host HAL for native tests: scripted RX bytes, captured TX bytes, a
 * manual clock, a fake EEPROM epoch cell and a stop pin. Test-only; fixed
 * buffers, no heap. */
#ifndef BHMS_HAL_HOST_H
#define BHMS_HAL_HOST_H
#include "bhms.h"

#define BHMS_HOST_RX_CAP 4096u
#define BHMS_HOST_TX_CAP 8192u

typedef struct {
    uint8_t rx[BHMS_HOST_RX_CAP];
    size_t rx_head, rx_len;
    uint8_t tx[BHMS_HOST_TX_CAP];
    size_t tx_len, tx_read;
    uint32_t now_ms;
    uint32_t eeprom; /* persisted epoch cell */
    int has_eeprom;  /* 0 => the HAL reports no persistent store */
    int store_fails; /* epoch_store returns failure */
    unsigned eeprom_writes;
    int pin; /* stop input level */
    int tx_per_millis; /* if nonzero, each uart_write advances the clock by this many ms */
    bhms_hal hal;
} bhms_host;

/* Initialise and populate host->hal. */
void bhms_host_init(bhms_host *h, int persistent_epoch);
/* Queue bytes for the endpoint to read. Returns 0 or -1 when the queue is full. */
int bhms_host_feed(bhms_host *h, const uint8_t *bytes, size_t n);
/* Wrap payload in an HM frame (gateway side) and queue it. */
int bhms_host_feed_frame(bhms_host *h, uint8_t kind, uint8_t channel, uint64_t session,
                         uint32_t sequence, const uint8_t *payload, size_t n);

typedef struct {
    uint8_t kind, channel;
    uint64_t session;
    uint32_t sequence;
    uint16_t length;
    uint8_t payload[HMS_FRAME_PAYLOAD];
} bhms_host_frame;

/* Parse the next frame the endpoint transmitted (using the reused C parser).
 * Returns 1 and fills out, 0 when no complete frame remains, -1 on a corrupt
 * frame (skipped). */
int bhms_host_next_tx(bhms_host *h, bhms_host_frame *out);
/* Number of captured bytes not yet consumed by bhms_host_next_tx. */
size_t bhms_host_tx_pending(const bhms_host *h);
#endif
