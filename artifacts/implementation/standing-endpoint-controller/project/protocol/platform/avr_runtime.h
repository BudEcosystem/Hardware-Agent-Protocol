#ifndef HMS_AVR_RUNTIME_H
#define HMS_AVR_RUNTIME_H
#include "avr_uart.h"
#include "avr_usart.h"
#include "avr_clock.h"
#include "avr_eeprom.h"
#include "boot_epoch.h"

/* Immutable installation, not received over UART. The underlying callbacks
 * remain trusted installed code. This composition wraps their clock callback
 * with the actual Timer1 implementation; it never fabricates qualification.
 * A successful reservation/readback does not establish boot_storage_assured.
 * mode_flags may contain RECONCILE and either SIMULATOR_ONLY or commissioned
 * PHYSICAL_COMMISSIONED with optional STOP_COMMISSIONED. Physical assurance is
 * an external board-specific obligation, never granted by this library. */
typedef struct {
    const hms_ep_config *primitive;
    uint32_t receive_budget_ms; /* explicit 1..0x7fffffff, no synthetic default */
    uint16_t eeprom_poll_budget, boot_capacity, ubrr;
    uint16_t mode_flags;
    uint8_t double_speed, boot_storage_assured, clock_assurances;
} hms_avr_runtime_config;

typedef struct {
    hms_endpoint endpoint;
    hms_endpoint_link link;
    hms_avr_uart receive;
    hms_avr_usart usart;
    hms_avr_clock clock;
    hms_avr_eeprom eeprom;
    hms_boot_storage storage;
    hms_boot_reservation boot;
    hms_ep_config callbacks;
    const hms_avr_runtime_config *installed;
    uint64_t service_tick;
    uint16_t flags;
    uint8_t started, foreground_active, clock_lost, transport_fault, receive_closed;
} hms_avr_runtime;

/* Requires a zero-initialized static object in a fresh inhibited boot domain,
 * global interrupts disabled, exclusive USART0/Timer1/EEPROM ownership and the
 * pre-provisioned finite EEPROM bank. Startup is one-shot. No formatting or
 * erase occurs. Callers enable global interrupts only after successful setup;
 * exactly one non-nesting RX vector and Timer1 overflow vector call the helpers.
 * Success means software/hardware setup completed, NOT ordinary eligibility.
 * In particular missing assurance leaves endpoint flags inhibited. */
uint8_t hms_avr_runtime_start(hms_avr_runtime *runtime, const hms_avr_runtime_config *config);
void hms_avr_runtime_receive_irq(hms_avr_runtime *runtime);
void hms_avr_runtime_overflow_irq(hms_avr_runtime *runtime);
/* One received byte, at most one endpoint driver callback, at most one TX byte.
 * Empty RX and stalled TX cannot postpone clock/deadline/endpoint servicing.
 * RX errors reset only transport assembly. Clock failure closes RX admission
 * and services the installed endpoint loss response; independent physical stop
 * and an independently timed degraded transport remain installation work.
 * Receive budget is foreground assembly time, not wire arrival age: the RX
 * queue stores no acquisition timestamps. Actual service/interrupt latency and
 * the Timer1 strict overflow bound must be established for a physical board. */
void hms_avr_runtime_step(hms_avr_runtime *runtime);
#endif
