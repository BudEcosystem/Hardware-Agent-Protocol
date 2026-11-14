/* BHMS-Compact binding: C endpoint library (spec/bhms/11-compact-binding.md).
 *
 * Lets a small microcontroller be a BHMS device: a static capability table, a
 * replay ring, boot-epoch handling, fences and a stop path, over the HDLC-style
 * `HM` frames of protocol/serial/frame.h. No heap; every bound is a macro in
 * bhms_config.h. C99, no RTTI/exceptions, compiles as C++ too (Arduino).
 *
 * Minimal use:
 *
 *   BHMS_FIELDS(led_args) = { BHMS_BOOL() };
 *   static const bhms_action actions[] BHMS_PROGMEM = {
 *       BHMS_ACTION(led_run, 0, 0, BHMS_FIELDS_REF(led_args), BHMS_NO_FIELDS) };
 *   static const bhms_property props[] BHMS_PROGMEM = {
 *       BHMS_PROPERTY(adc_read, BHMS_U16) };
 *   static const bhms_device dev = { {digest8...}, BHMS_DEV_FENCING,
 *       actions, 1, props, 1, 0, 0 };
 *   bhms_endpoint ep;  bhms_init(&ep, &dev, &hal);  for (;;) bhms_poll(&ep);
 *
 * Thread-safety: one owner; no function is reentrant or interrupt-safe.
 */
#ifndef BHMS_H
#define BHMS_H

#include <stddef.h>
#include <stdint.h>

#include "bhms_config.h"
#include "bhms_hal.h"
#include "frame.h" /* protocol/serial/frame.h: the HM frame parser, reused unchanged */

#ifdef __cplusplus
extern "C" {
#endif

/* ---- Flash placement (AVR keeps constant tables out of RAM) ---------------- */
#if defined(__AVR__)
#include <avr/pgmspace.h>
#define BHMS_PROGMEM PROGMEM
#else
#define BHMS_PROGMEM
#endif

/* ---- Wire constants --------------------------------------------------------- */
#define BHMS_CHANNEL 1u
#define BHMS_VERSION 2u /* 2: STOP and STOP_ACK carry a correlation token (BHMS-CMP-050) */
#define BHMS_KIND_CONTROL 1u
#define BHMS_KIND_STATUS 2u
#define BHMS_KIND_TELEMETRY 3u

enum {
    BHMS_MSG_HELLO_REQ = 0x01, BHMS_MSG_INVOKE = 0x02, BHMS_MSG_CANCEL = 0x03,
    BHMS_MSG_READ = 0x04, BHMS_MSG_STOP = 0x05, BHMS_MSG_QUERY = 0x06,
    BHMS_MSG_HELLO = 0x81, BHMS_MSG_STATUS = 0x82, BHMS_MSG_RESULT = 0x83,
    BHMS_MSG_VALUE = 0x84, BHMS_MSG_STOP_ACK = 0x85, BHMS_MSG_ERROR = 0xFF
};

/* HELLO_REQ flags / HELLO flags. */
#define BHMS_HELLO_REQ_NEW_SESSION 0x01u
#define BHMS_HELLO_FENCING 0x01u
#define BHMS_HELLO_PERSISTENT_EPOCH 0x02u
#define BHMS_HELLO_STOP_SUPPORTED 0x04u

/* Operation states (STATUS.state / RESULT.state). */
enum { BHMS_ST_ACCEPTED = 1, BHMS_ST_RUNNING = 2, BHMS_ST_COMPLETED = 3,
       BHMS_ST_FAILED = 4, BHMS_ST_CANCELED = 5, BHMS_ST_REJECTED = 6 };
/* STATUS.cancel. */
enum { BHMS_CANCEL_NONE = 0, BHMS_CANCEL_REQUESTED = 1, BHMS_CANCEL_ACK = 2,
       BHMS_CANCEL_REFUSED = 3, BHMS_CANCEL_CONFIRMED = 4 };
#define BHMS_PROGRESS_UNKNOWN 255u
/* RESULT.evidence. */
enum { BHMS_EV_NONE = 0, BHMS_EV_REPORTED = 1, BHMS_EV_MEASURED = 2 };
/* VALUE.quality / VALUE.evidence. */
enum { BHMS_Q_VALID = 0, BHMS_Q_STALE = 1, BHMS_Q_INVALID = 2, BHMS_Q_UNKNOWN = 3 };
enum { BHMS_VEV_MEASURED = 0, BHMS_VEV_REPORTED = 1, BHMS_VEV_COMMANDED = 2,
       BHMS_VEV_ESTIMATED = 3, BHMS_VEV_SIMULATED = 4 };
#define BHMS_AGE_UNKNOWN 0xFFFFFFFFu
/* READ flags. */
#define BHMS_READ_FRESH 0x01u
/* STOP reasons and STOP_ACK outcomes. */
enum { BHMS_STOP_UNSPECIFIED = 0, BHMS_STOP_OPERATOR = 1, BHMS_STOP_CLIENT = 2,
       BHMS_STOP_GATEWAY = 3 };
enum { BHMS_STOPACK_INITIATED = 0, BHMS_STOPACK_CONFIRMED = 1, BHMS_STOPACK_UNSUPPORTED = 2 };

/* ERROR codes. */
enum {
    BHMS_E_MALFORMED = 1, BHMS_E_UNKNOWN_ACTION = 2, BHMS_E_UNKNOWN_PROPERTY = 3,
    BHMS_E_OUT_OF_RANGE = 4, BHMS_E_FENCED = 5, BHMS_E_LEASE_REQUIRED = 6,
    BHMS_E_BUSY = 7, BHMS_E_HANDLE_UNKNOWN = 8, BHMS_E_SESSION_MISMATCH = 9,
    BHMS_E_EXPIRED = 10, BHMS_E_UNSUPPORTED = 11, BHMS_E_PRECONDITION = 12,
    BHMS_E_INHIBITED = 13, BHMS_E_HANDLE_CONFLICT = 14, BHMS_E_INTERNAL = 15
};

/* Exact payload lengths of fixed-size messages. */
#define BHMS_LEN_HELLO_REQ 7u
#define BHMS_LEN_HELLO 24u
#define BHMS_LEN_INVOKE_FIXED 10u
#define BHMS_LEN_CANCEL 3u
#define BHMS_LEN_READ 5u
#define BHMS_LEN_STOP 3u
#define BHMS_LEN_QUERY 3u
#define BHMS_LEN_STATUS 6u
#define BHMS_LEN_RESULT_FIXED 6u
#define BHMS_LEN_VALUE_FIXED 14u
#define BHMS_LEN_STOP_ACK 5u
#define BHMS_LEN_ERROR 6u

/* ---- Value types and the capability table ----------------------------------- */
typedef enum { BHMS_U8 = 1, BHMS_I8, BHMS_U16, BHMS_I16, BHMS_U32, BHMS_I32,
               BHMS_F32, BHMS_BOOL } bhms_type;

/* A decoded field value. Integer types sign/zero-extend into i/u; bool is 0/1. */
typedef union { uint32_t u; int32_t i; float f; } bhms_value;

/* Wire width in bytes of a type; 0 for an invalid type code. */
uint8_t bhms_type_width(uint8_t type);

/* One argument/result/property field. Local limits are in WIRE units (a field
 * with scale 0.1 and a limit of 500 means 50.0). Integer limits use ilo/ihi
 * (u32 limits are reinterpreted as uint32); f32 limits use flo/fhi. */
typedef struct {
    uint8_t type;
    uint8_t has_range;
    int32_t ilo, ihi;
    float flo, fhi;
} bhms_field;

#define BHMS_INT_FIELD(t) { (t), 0, 0, 0, 0.0f, 0.0f }
#define BHMS_INT_RANGE(t, lo, hi) { (t), 1, (int32_t)(lo), (int32_t)(hi), 0.0f, 0.0f }
#define BHMS_U8() BHMS_INT_FIELD(BHMS_U8)
#define BHMS_I8() BHMS_INT_FIELD(BHMS_I8)
#define BHMS_U16() BHMS_INT_FIELD(BHMS_U16)
#define BHMS_I16() BHMS_INT_FIELD(BHMS_I16)
#define BHMS_U32() BHMS_INT_FIELD(BHMS_U32)
#define BHMS_I32() BHMS_INT_FIELD(BHMS_I32)
#define BHMS_BOOL() BHMS_INT_FIELD(BHMS_BOOL)
#define BHMS_F32() { BHMS_F32, 0, 0, 0, 0.0f, 0.0f }
#define BHMS_U8_RANGE(lo, hi) BHMS_INT_RANGE(BHMS_U8, lo, hi)
#define BHMS_I8_RANGE(lo, hi) BHMS_INT_RANGE(BHMS_I8, lo, hi)
#define BHMS_U16_RANGE(lo, hi) BHMS_INT_RANGE(BHMS_U16, lo, hi)
#define BHMS_I16_RANGE(lo, hi) BHMS_INT_RANGE(BHMS_I16, lo, hi)
#define BHMS_U32_RANGE(lo, hi) BHMS_INT_RANGE(BHMS_U32, lo, hi)
#define BHMS_I32_RANGE(lo, hi) BHMS_INT_RANGE(BHMS_I32, lo, hi)
#define BHMS_F32_RANGE(lo, hi) { BHMS_F32, 1, 0, 0, (float)(lo), (float)(hi) }

/* Field array declaration and reference helpers:
 *   BHMS_FIELDS(move_args) = { BHMS_F32_RANGE(0, 200), BHMS_U16() };
 *   BHMS_ACTION(run, cancel, flags, BHMS_FIELDS_REF(move_args), BHMS_NO_FIELDS) */
#define BHMS_FIELDS(name) static const bhms_field name[] BHMS_PROGMEM
#define BHMS_FIELDS_REF(name) name, (uint8_t)(sizeof(name) / sizeof((name)[0]))
#define BHMS_NO_FIELDS 0, 0

/* What an action run callback receives and returns. */
typedef struct {
    bhms_value results[BHMS_MAX_FIELDS]; /* fill n_results entries on DONE */
    uint16_t handle;                     /* the operation's handle */
    uint8_t evidence;                    /* BHMS_EV_* on DONE/FAILED */
    uint8_t fault;                       /* device fault number on FAILED */
    uint8_t error;                       /* BHMS_E_* on REJECTED (default PRECONDITION) */
    uint8_t detail;                      /* ERROR.detail on REJECTED (default 0): lets a
                                          * callback name the limit or condition it refused */
} bhms_call;

enum {
    BHMS_RUN_DONE = 0,     /* finished synchronously: RESULT completed */
    BHMS_RUN_STARTED = 1,  /* running; the app later calls bhms_op_finish */
    BHMS_RUN_FAILED = 2,   /* RESULT failed with call->fault */
    BHMS_RUN_REJECTED = 3  /* not started: ERROR call->error, no operation */
};

typedef uint8_t (*bhms_action_fn)(void *user, const bhms_value *args, bhms_call *call);
/* Returns BHMS_CANCEL_ACK (the app will bhms_op_finish later), _CONFIRMED (the
 * operation ended now) or _REFUSED. */
typedef uint8_t (*bhms_cancel_fn)(void *user, uint16_t handle);

#define BHMS_ACT_REQUIRES_LEASE 0x01u /* BHMS-CMP-040: fence 0 => LEASE_REQUIRED */

typedef struct {
    bhms_action_fn run;
    bhms_cancel_fn cancel; /* NULL: cancellation refused */
    uint8_t flags;
    const bhms_field *args;
    uint8_t n_args;
    const bhms_field *results;
    uint8_t n_results;
} bhms_action;

#define BHMS_ACTION(run, cancel, flags, args, results) { run, cancel, flags, args, results }

/* Sample metadata a property read reports. */
typedef struct {
    uint8_t evidence;  /* BHMS_VEV_* */
    uint32_t age_ms;   /* BHMS_AGE_UNKNOWN when not known */
} bhms_sample;

/* Returns BHMS_Q_*; on INVALID/UNKNOWN the value is not sent (BHMS-CMP-060).
 * `fresh` is set when the reader demanded a fresh measurement. */
typedef uint8_t (*bhms_read_fn)(void *user, uint8_t fresh, bhms_value *out, bhms_sample *meta);

typedef struct {
    bhms_read_fn read;
    bhms_field field; /* type and local limits (used for result sanity only) */
} bhms_property;

#define BHMS_PROPERTY(read, type) { read, { (type), 0, 0, 0, 0.0f, 0.0f } }

/* Stop procedure: make the device safe. Returns BHMS_STOPACK_INITIATED (call
 * bhms_stop_confirmed when safe) or _CONFIRMED; *evidence = BHMS_EV_*. */
typedef uint8_t (*bhms_stop_fn)(void *user, uint8_t reason, uint8_t *evidence);

#define BHMS_DEV_FENCING 0x01u

typedef struct {
    uint8_t digest8[8];        /* first 8 bytes of the description sha256 */
    uint8_t flags;             /* BHMS_DEV_* */
    const bhms_action *actions;
    uint8_t n_actions;
    const bhms_property *properties;
    uint8_t n_properties;
    bhms_stop_fn stop;         /* NULL => STOP_SUPPORTED not advertised */
    void *user;                /* passed to every callback */
} bhms_device;

/* ---- Endpoint state (caller-owned, static) ---------------------------------- */
#define BHMS_INV_FIXED 7u /* action, fence, ttl: INVOKE payload bytes 3..9 */

typedef struct {
    uint32_t stamp;                        /* acceptance order, 0 = free */
    uint16_t handle;
    uint8_t state, cancel, progress, evidence, fault;
    uint8_t inv_len, res_len;
    uint8_t inv[BHMS_INV_FIXED + BHMS_MAX_ARGS];
    uint8_t res[BHMS_MAX_RESULT];
} bhms_entry;

typedef struct bhms_endpoint {
    const bhms_device *dev;
    const bhms_hal *hal;
    hms_frame_parser parser;
    uint32_t epoch;
    uint32_t tx_seq;
    uint32_t fence_floor, max_fence;
    uint32_t value_seq;
    uint32_t stamp_clock;
    uint32_t frame_start_ms, last_rx_ms;
    uint16_t last_handle;
    uint16_t bad_frames; /* diagnostic: frames dropped by the framing layer */
    uint8_t persistent, inhibit, pin_asserted, stop_pending, stop_count, stop_token, rx_started;
    uint8_t max_args;
    bhms_entry ring[BHMS_RING_SIZE];
} bhms_endpoint;

typedef enum {
    BHMS_OK = 0,
    BHMS_ERR_INVALID = -1,  /* bad table/HAL, or a layout exceeds a configured bound */
    BHMS_ERR_NO_ENTRY = -2, /* handle not in the ring */
    BHMS_ERR_STATE = -3     /* operation not in a state that allows this call */
} bhms_err;

/* Validate the table and HAL, derive and persist the boot epoch (before any
 * effect is possible: bhms_init must run before actions can be invoked), clear
 * all state. Does not transmit; the gateway opens with HELLO_REQ.
 * Returns BHMS_ERR_INVALID if any action layout needs more than BHMS_MAX_ARGS /
 * BHMS_MAX_RESULT / BHMS_MAX_FIELDS, or a mandatory hook is missing. */
bhms_err bhms_init(bhms_endpoint *ep, const bhms_device *dev, const bhms_hal *hal);

/* Service the link: drain up to BHMS_POLL_MAX_BYTES from the UART, process
 * complete frames, enforce the frame deadline, watch the stop pin. Call often:
 * a 64-byte UART RX buffer fills in about 5.5 ms at 115200 baud (10 bits per
 * byte), so the gap between polls, INCLUDING any callback run inside bhms_poll,
 * must stay under that or bytes (possibly a STOP frame) are lost. Callbacks that
 * can take longer than about 5 ms must return BHMS_RUN_STARTED and work from the
 * main loop. Scale the figure with baud rate and buffer size. */
void bhms_poll(bhms_endpoint *ep);

/* Finish an asynchronous operation (after BHMS_RUN_STARTED or a cancel ACK):
 * state is BHMS_ST_COMPLETED/FAILED/CANCELED/REJECTED; `results` is read only
 * for COMPLETED. Sends RESULT (kind telemetry) once. */
bhms_err bhms_op_finish(bhms_endpoint *ep, uint16_t handle, uint8_t state,
                        uint8_t evidence, uint8_t fault, const bhms_value *results);
/* Record progress 0..100 and send an unsolicited STATUS. */
bhms_err bhms_op_progress(bhms_endpoint *ep, uint16_t handle, uint8_t percent);
/* Send an unsolicited VALUE (kind telemetry, request 0) for a property. */
bhms_err bhms_publish(bhms_endpoint *ep, uint8_t property_index);
/* After a stop returned INITIATED: send the second STOP_ACK (confirmed). */
void bhms_stop_confirmed(bhms_endpoint *ep, uint8_t evidence);
/* Latch/clear a device fault inhibit: while set, INVOKE answers INHIBITED. */
void bhms_set_inhibit(bhms_endpoint *ep, uint8_t inhibited);

/* ---- Message codecs (exact layouts of spec §11.2; little-endian payloads) ---- */
/* Each encoder writes the payload to buf (caller guarantees capacity) and
 * returns its length. They never pad (BHMS-CMP-003). */
size_t bhms_enc_hello_req(uint8_t *buf, uint8_t flags, uint32_t nonce);
size_t bhms_enc_hello(uint8_t *buf, uint8_t flags, const uint8_t digest8[8], uint32_t epoch,
                      uint32_t nonce, uint16_t last_handle, uint8_t ring, uint8_t max_active,
                      uint8_t max_args);
size_t bhms_enc_invoke(uint8_t *buf, uint16_t handle, uint8_t action, uint32_t fence,
                       uint16_t ttl_ms, const uint8_t *args, size_t n_args);
size_t bhms_enc_cancel(uint8_t *buf, uint16_t handle);
size_t bhms_enc_query(uint8_t *buf, uint16_t handle);
size_t bhms_enc_read(uint8_t *buf, uint16_t request, uint8_t property, uint8_t flags);
/* `token` != 0 is chosen by the gateway and echoed by both STOP_ACKs; 0 is reserved for stops the endpoint starts itself. */
size_t bhms_enc_stop(uint8_t *buf, uint8_t reason, uint8_t token);
size_t bhms_enc_status(uint8_t *buf, uint16_t handle, uint8_t state, uint8_t cancel,
                       uint8_t progress);
size_t bhms_enc_result(uint8_t *buf, uint16_t handle, uint8_t state, uint8_t evidence,
                       uint8_t fault, const uint8_t *fields, size_t n_fields);
size_t bhms_enc_value(uint8_t *buf, uint16_t request, uint8_t property, uint8_t quality,
                      uint8_t evidence, uint32_t sequence, uint32_t age_ms,
                      const uint8_t *value, size_t n_value);
size_t bhms_enc_stop_ack(uint8_t *buf, uint8_t outcome, uint8_t evidence, uint8_t canceled, uint8_t token);
size_t bhms_enc_error(uint8_t *buf, uint8_t request_type, uint16_t id, uint8_t code,
                      uint8_t detail);

/* Decoded views. Decoders return 0 on success, -1 when the length or type byte
 * does not match the message exactly (BHMS-CMP-002). Variable parts point into
 * the payload. */
typedef struct { uint8_t version, flags; uint32_t nonce; } bhms_hello_req;
typedef struct {
    uint8_t version, flags, digest8[8], ring, max_active, max_args;
    uint32_t epoch, nonce;
    uint16_t last_handle;
} bhms_hello;
typedef struct {
    uint16_t handle, ttl_ms;
    uint8_t action;
    uint32_t fence;
    const uint8_t *args;
    size_t n_args;
} bhms_invoke;
typedef struct { uint16_t handle; uint8_t state, cancel, progress; } bhms_status;
typedef struct {
    uint16_t handle;
    uint8_t state, evidence, fault;
    const uint8_t *fields;
    size_t n_fields;
} bhms_result;
typedef struct {
    uint16_t request;
    uint8_t property, quality, evidence;
    uint32_t sequence, age_ms;
    const uint8_t *value;
    size_t n_value;
} bhms_valuemsg;
typedef struct { uint8_t outcome, evidence, canceled, token; } bhms_stop_ack;
typedef struct { uint8_t request_type, code, detail; uint16_t id; } bhms_error;

int bhms_dec_hello_req(const uint8_t *p, size_t n, bhms_hello_req *out);
int bhms_dec_hello(const uint8_t *p, size_t n, bhms_hello *out);
int bhms_dec_invoke(const uint8_t *p, size_t n, bhms_invoke *out);
int bhms_dec_status(const uint8_t *p, size_t n, bhms_status *out);
int bhms_dec_result(const uint8_t *p, size_t n, bhms_result *out);
int bhms_dec_value(const uint8_t *p, size_t n, bhms_valuemsg *out);
int bhms_dec_stop_ack(const uint8_t *p, size_t n, bhms_stop_ack *out);
int bhms_dec_error(const uint8_t *p, size_t n, bhms_error *out);

/* Field value codec (§11.4). put writes bhms_type_width(type) bytes. get returns
 * 0, or -1 for a bool byte other than 0/1 or an invalid type. */
void bhms_value_put(uint8_t type, bhms_value v, uint8_t *out);
int bhms_value_get(uint8_t type, const uint8_t *in, bhms_value *out);

/* ---- Frame transmit (the framing layer's encoder side) ---------------------- */
/* Largest decoded payload this library emits. */
#define BHMS_TX_PAYLOAD_MAX \
    ((BHMS_LEN_RESULT_FIXED + BHMS_MAX_RESULT) > BHMS_LEN_HELLO ? \
     (BHMS_LEN_RESULT_FIXED + BHMS_MAX_RESULT) : BHMS_LEN_HELLO)
#define BHMS_TX_PAYLOAD_CAP (BHMS_TX_PAYLOAD_MAX + 16u)
/* Host-side helper: encode a whole frame into out (capacity HMS_FRAME_WIRE_MAX
 * suffices); returns the wire length including both flags, or 0 on bad args. */
size_t bhms_frame_encode(uint8_t *out, size_t cap, uint8_t kind, uint8_t channel,
                         uint64_t session, uint32_t sequence, const uint8_t *payload,
                         size_t n_payload);
/* Embedded helper: stream a frame through the HAL in small chunks, no big buffer. */
void bhms_frame_send(const bhms_hal *hal, uint8_t kind, uint8_t channel, uint64_t session,
                     uint32_t sequence, const uint8_t *payload, size_t n_payload);

#ifdef __cplusplus
}
#endif
#endif
